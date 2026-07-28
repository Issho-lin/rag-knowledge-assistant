"""Chroma 向量库：embedding + 余弦相似度检索。

自行封装以便：统一走配置里的网关与模型、控制重试、后续可换成其它向量库。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from langchain_openai import OpenAIEmbeddings

from ..config import get_settings
from ..exceptions import NonRetryableLLMError, RetryableLLMError
from ..logging import get_logger

log = get_logger(__name__)

_COLLECTION = "corpus"
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class VectorStore:
    def __init__(self, chroma_path: Path | None = None) -> None:
        s = get_settings()
        path = chroma_path if chroma_path is not None else s.chroma_path
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._embed = OpenAIEmbeddings(
            model=s.embedding_model,
            api_key=s.openai_api_key,
            base_url=s.openai_base_url,
            max_retries=0,
            # 国内 MaaS / DashScope 兼容接口需要直接传字符串，不能走 tiktoken 预处理
            check_embedding_ctx_length=False,
        )
        self._coll = self._client.get_or_create_collection(
            name=_COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            return self._embed.embed_documents(texts)
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if status is not None and status not in _RETRYABLE_STATUS:
                raise NonRetryableLLMError(str(exc)) from exc
            raise RetryableLLMError(str(exc)) from exc

    def add(
        self,
        chunks: list[str],
        sources: list[str],
        *,
        ids: list[str] | None = None,
        batch_size: int = 20,
    ) -> int:
        """对 chunk 做 embedding 并 upsert。ids 可选；不传则按内容哈希生成。

        国内部分 embedding 网关限制单批 ≤20，故按 batch_size 分批。
        """
        if not chunks:
            return 0
        if ids is None:
            ids = [f"c{i}_{abs(hash(s)) % 10**10}" for i, s in enumerate(chunks)]
        if not (len(ids) == len(chunks) == len(sources)):
            raise ValueError("ids/chunks/sources 长度必须一致")

        total = 0
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            batch_ids = ids[start:end]
            batch_chunks = chunks[start:end]
            batch_sources = sources[start:end]
            embeddings = self._embed_texts(batch_chunks)
            self._coll.upsert(
                ids=batch_ids,
                documents=batch_chunks,
                embeddings=embeddings,
                metadatas=[{"source": src} for src in batch_sources],
            )
            total += len(batch_chunks)
        log.info("vector.add", count=total, batch_size=batch_size)
        return total

    def query(self, text: str, k: int = 4) -> list[dict[str, Any]]:
        """返回 top-k 片段：[{id, text, source, score}, ...]。"""
        n = min(k, max(self.count(), 1))
        qvec = self._embed_texts([text])[0]
        res = self._coll.query(query_embeddings=[qvec], n_results=n)
        out: list[dict[str, Any]] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc_id, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append(
                {
                    "id": doc_id,
                    "text": doc,
                    "source": meta.get("source", "?"),
                    "score": 1.0 - dist,
                }
            )
        return out

    def count(self) -> int:
        try:
            return self._coll.count()
        except Exception:
            return 0
