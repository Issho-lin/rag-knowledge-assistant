"""Chroma 向量库（教学 / CI fallback）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import chromadb

from ..core.config import get_settings
from ..core.logging import get_logger
from .embeddings import embed_documents
from .filters import chroma_where
from .metadata import chunk_from_hit

log = get_logger(__name__)

_DEFAULT_COLLECTION = "corpus"


class VectorStoreBackend(Protocol):
    def add(
        self,
        chunks: list[str],
        sources: list[str],
        *,
        ids: list[str] | None = None,
        metadatas: list[dict[str, str | int]] | None = None,
        batch_size: int = 20,
    ) -> int: ...

    def query(
        self,
        text: str,
        k: int = 4,
        *,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def count(self) -> int: ...

    def list_doc_fingerprints(self) -> dict[str, tuple[str, str]]: ...

    def delete_by_doc_ids(self, doc_ids: list[str]) -> int: ...

    def purge_unfingerprinted(self) -> int: ...

    def scroll_records(self) -> list[dict[str, Any]]: ...


class ChromaVectorStore:
    def __init__(
        self,
        chroma_path: Path | None = None,
        *,
        collection_name: str | None = None,
    ) -> None:
        s = get_settings()
        path = chroma_path if chroma_path is not None else s.chroma_path
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        coll_name = collection_name or _DEFAULT_COLLECTION
        self._coll = self._client.get_or_create_collection(
            name=coll_name, metadata={"hnsw:space": "cosine"}
        )

    def add(
        self,
        chunks: list[str],
        sources: list[str],
        *,
        ids: list[str] | None = None,
        metadatas: list[dict[str, str | int]] | None = None,
        batch_size: int = 20,
    ) -> int:
        if not chunks:
            return 0
        if ids is None:
            ids = [f"c{i}_{abs(hash(s)) % 10**10}" for i, s in enumerate(chunks)]
        if not (len(ids) == len(chunks) == len(sources)):
            raise ValueError("ids/chunks/sources 长度必须一致")
        if metadatas is not None and len(metadatas) != len(chunks):
            raise ValueError("metadatas 长度必须与 chunks 一致")

        total = 0
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            batch_ids = ids[start:end]
            batch_chunks = chunks[start:end]
            batch_sources = sources[start:end]
            batch_meta = (
                metadatas[start:end]
                if metadatas is not None
                else [{"source": src} for src in batch_sources]
            )
            embeddings = embed_documents(batch_chunks)
            self._coll.upsert(
                ids=batch_ids,
                documents=batch_chunks,
                embeddings=embeddings,
                metadatas=batch_meta,
            )
            total += len(batch_chunks)
        log.info("vector.chroma.add", count=total, batch_size=batch_size)
        return total

    def query(
        self,
        text: str,
        k: int = 4,
        *,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        where = chroma_where(metadata_filter) if metadata_filter else None
        if self.count() == 0:
            return []
        qvec = embed_documents([text])[0]
        query_kwargs: dict[str, Any] = {
            "query_embeddings": [qvec],
            "n_results": k,
        }
        if where is not None:
            query_kwargs["where"] = where
        res = self._coll.query(**query_kwargs)
        out: list[dict[str, Any]] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc_id, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append(chunk_from_hit(meta or {}, text=doc, doc_id=doc_id, score=1.0 - dist))
        return out

    def count(self) -> int:
        try:
            return self._coll.count()
        except Exception:
            return 0

    def scroll_records(self) -> list[dict[str, Any]]:
        if self.count() == 0:
            return []
        data = self._coll.get(include=["documents", "metadatas"])
        out: list[dict[str, Any]] = []
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        for cid, doc, meta in zip(ids, docs, metas):
            out.append(chunk_from_hit(meta or {}, text=doc or "", doc_id=cid, score=0.0))
        return out

    def list_doc_fingerprints(self) -> dict[str, tuple[str, str]]:
        """doc_id -> (file_hash, corpus)。无 doc_id 的遗留 chunk 不计入。"""
        if self.count() == 0:
            return {}
        data = self._coll.get(include=["metadatas"])
        out: dict[str, tuple[str, str]] = {}
        for meta in data.get("metadatas") or []:
            if not meta:
                continue
            doc_id = str(meta.get("doc_id") or "")
            if not doc_id:
                continue
            out[doc_id] = (str(meta.get("file_hash") or ""), str(meta.get("corpus") or ""))
        return out

    def delete_by_doc_ids(self, doc_ids: list[str]) -> int:
        ids = [d for d in doc_ids if d]
        if not ids or self.count() == 0:
            return 0
        before = self.count()
        for start in range(0, len(ids), 100):
            batch = ids[start : start + 100]
            self._coll.delete(where={"doc_id": {"$in": batch}})
        return max(0, before - self.count())

    def purge_unfingerprinted(self) -> int:
        """删除没有 doc_id 的遗留 chunk，避免增量与旧全量索引叠两份。"""
        if self.count() == 0:
            return 0
        data = self._coll.get(include=["metadatas"])
        orphan_ids = [
            cid
            for cid, meta in zip(data.get("ids") or [], data.get("metadatas") or [])
            if not (meta or {}).get("doc_id")
        ]
        if not orphan_ids:
            return 0
        self._coll.delete(ids=orphan_ids)
        log.info("vector.chroma.purge_unfingerprinted", count=len(orphan_ids))
        return len(orphan_ids)
