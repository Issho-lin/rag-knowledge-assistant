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

from ..logging import get_logger

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
        self._bm25: BM25Okapi | None = None
        if path.is_file():
            self._load()

    def _load(self) -> None:
        data = pickle.loads(self.path.read_bytes())
        self._ids = data["ids"]
        self._docs = data["docs"]
        self._sources = data["sources"]
        corpus = [tokenize(d) for d in self._docs]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        log.info("bm25.loaded", path=str(self.path), count=len(self._docs))

    def rebuild(self, ids: list[str], docs: list[str], sources: list[str]) -> int:
        if not (len(ids) == len(docs) == len(sources)):
            raise ValueError("ids/docs/sources 长度必须一致")
        self._ids = list(ids)
        self._docs = list(docs)
        self._sources = list(sources)
        corpus = [tokenize(d) for d in self._docs]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(
            pickle.dumps(
                {"ids": self._ids, "docs": self._docs, "sources": self._sources},
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        )
        log.info("bm25.rebuilt", path=str(self.path), count=len(self._docs))
        return len(self._docs)

    def query(self, text: str, k: int = 4) -> list[dict[str, Any]]:
        if not self._bm25 or not self._docs:
            return []
        tokens = tokenize(text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        # 取 top-k 下标
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        out: list[dict[str, Any]] = []
        for i in ranked:
            if scores[i] <= 0:
                continue
            out.append(
                {
                    "id": self._ids[i],
                    "text": self._docs[i],
                    "source": self._sources[i],
                    "score": float(scores[i]),
                }
            )
        return out

    def count(self) -> int:
        return len(self._docs)
