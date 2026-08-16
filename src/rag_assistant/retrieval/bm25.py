"""BM25 关键词检索：补向量检索在工号、专有名词上的短板。

中文用「拉丁词 + 单字」简单分词，不引入 jieba 依赖；对 XY003 / ITSM 这类 token 足够。
索引随 ingest 重建，落在向量库同级目录的 bm25.pkl。
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from ..core.logging import get_logger
from .filters import match_metadata
from .metadata import chunk_from_hit

log = get_logger(__name__)

# 英文/数字串 或 单个汉字
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:@-]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._ids: list[str] = []
        self._docs: list[str] = []
        self._sources: list[str] = []
        self._metadatas: list[dict[str, str | int]] = []
        self._bm25: BM25Okapi | None = None
        if path.is_file():
            self._load()

    def _load(self) -> None:
        # 加载BM25索引
        data = pickle.loads(self.path.read_bytes())
        self._ids = data["ids"]
        self._docs = data["docs"]
        self._sources = data["sources"]
        self._metadatas = data.get("metadatas", [{"source": s} for s in self._sources])
        corpus = [tokenize(d) for d in self._docs]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        log.info("bm25.loaded", path=str(self.path), count=len(self._docs))

    def rebuild(
        self,
        ids: list[str],
        docs: list[str],
        sources: list[str],
        *,
        metadatas: list[dict[str, str | int]] | None = None,
    ) -> int:
        # 如果ids/docs/sources长度不一致，则抛出异常
        if not (len(ids) == len(docs) == len(sources)):
            raise ValueError("ids/docs/sources 长度必须一致")
        # 如果metadatas长度不与docs一致，则抛出异常
        if metadatas is not None and len(metadatas) != len(docs):
            raise ValueError("metadatas 长度必须与 docs 一致")
        # 更新索引
        self._ids = list(ids)
        self._docs = list(docs)
        self._sources = list(sources)
        self._metadatas = (
            list(metadatas) if metadatas is not None else [{"source": s} for s in sources]
        )
        self._commit()
        log.info("bm25.rebuilt", path=str(self.path), count=len(self._docs))
        return len(self._docs)

    def upsert(
        self,
        ids: list[str],
        docs: list[str],
        sources: list[str],
        *,
        metadatas: list[dict[str, str | int]] | None = None,
    ) -> int:
        if not ids:
            return 0
        if not (len(ids) == len(docs) == len(sources)):
            raise ValueError("ids/docs/sources 长度必须一致")
        if metadatas is not None and len(metadatas) != len(docs):
            raise ValueError("metadatas 长度必须与 docs 一致")
        meta = list(metadatas) if metadatas is not None else [{"source": s} for s in sources]
        self._ids.extend(ids)
        self._docs.extend(docs)
        self._sources.extend(sources)
        self._metadatas.extend(meta)
        self._commit()
        log.info("bm25.upserted", path=str(self.path), added=len(ids), count=len(self._docs))
        return len(ids)

    def delete_by_doc_ids(self, doc_ids: list[str]) -> int:
        drop = {d for d in doc_ids if d}
        if not drop or not self._ids:
            return 0
        keep = [
            i
            for i, meta in enumerate(self._metadatas)
            if str(meta.get("doc_id", "")) not in drop
        ]
        removed = len(self._ids) - len(keep)
        if removed == 0:
            return 0
        self._ids = [self._ids[i] for i in keep]
        self._docs = [self._docs[i] for i in keep]
        self._sources = [self._sources[i] for i in keep]
        self._metadatas = [self._metadatas[i] for i in keep]
        self._commit()
        log.info("bm25.deleted_by_doc_id", path=str(self.path), removed=removed)
        return removed

    def purge_unfingerprinted(self) -> int:
        if not self._ids:
            return 0
        keep = [i for i, meta in enumerate(self._metadatas) if meta.get("doc_id")]
        removed = len(self._ids) - len(keep)
        if removed == 0:
            return 0
        self._ids = [self._ids[i] for i in keep]
        self._docs = [self._docs[i] for i in keep]
        self._sources = [self._sources[i] for i in keep]
        self._metadatas = [self._metadatas[i] for i in keep]
        self._commit()
        log.info("bm25.purge_unfingerprinted", path=str(self.path), removed=removed)
        return removed

    def _commit(self) -> None:
        corpus = [tokenize(d) for d in self._docs]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(
            pickle.dumps(
                {
                    "ids": self._ids,
                    "docs": self._docs,
                    "sources": self._sources,
                    "metadatas": self._metadatas,
                },
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        )

    def query(
        self,
        text: str,
        k: int = 4,
        *,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self._bm25 or not self._docs:
            return []
        tokens = tokenize(text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        indices = range(len(scores))
        if metadata_filter:
            indices = [
                i
                for i in indices
                if match_metadata(
                    self._metadatas[i] if i < len(self._metadatas) else {"source": self._sources[i]},
                    metadata_filter,
                )
            ]
        ranked = sorted(indices, key=lambda i: scores[i], reverse=True)
        out: list[dict[str, Any]] = []
        for i in ranked:
            if scores[i] <= 0:
                continue
            meta = self._metadatas[i] if i < len(self._metadatas) else {"source": self._sources[i]}
            # 转换为统一chunk结构
            out.append(
                chunk_from_hit(
                    meta,
                    text=self._docs[i],
                    doc_id=self._ids[i],
                    score=float(scores[i]),
                )
            )
            if len(out) >= k:
                break
        return out

    def count(self) -> int:
        return len(self._docs)
