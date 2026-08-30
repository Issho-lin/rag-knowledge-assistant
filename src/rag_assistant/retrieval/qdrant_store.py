"""Qdrant 向量库（生产默认）。"""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    IsEmptyCondition,
    MatchAny,
    MatchValue,
    PayloadField,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from ..core.config import get_settings
from ..core.logging import get_logger
from .embeddings import embed_documents, embedding_dimension
from .metadata import chunk_from_hit

log = get_logger(__name__)


def _point_id(chunk_id: str) -> str:
    """Qdrant point id 须为 UUID 或 uint；用确定性 UUID 保持与 chunk id 可对照。"""
    return str(uuid5(NAMESPACE_URL, chunk_id))


def _qdrant_filter(metadata_filter: dict[str, str] | None) -> Filter | None:
    if not metadata_filter:
        return None
    return Filter(
        must=[FieldCondition(key=k, match=MatchValue(value=v)) for k, v in metadata_filter.items()]
    )


class QdrantVectorStore:
    def __init__(self, *, collection_name: str | None = None) -> None:
        s = get_settings()
        self._collection = collection_name or s.qdrant_collection
        self._client = QdrantClient(url=s.qdrant_url)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        names = {c.name for c in self._client.get_collections().collections}
        if self._collection in names:
            self._ensure_payload_index()
            return
        dim = embedding_dimension()
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        log.info("vector.qdrant.collection_created", name=self._collection, dim=dim)
        self._ensure_payload_index()

    def _ensure_payload_index(self) -> None:
        try:
            self._client.create_payload_index(
                collection_name=self._collection,
                field_name="doc_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass

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
            vectors = embed_documents(batch_chunks)
            points = []
            for chunk_id, doc, src, meta, vec in zip(
                batch_ids, batch_chunks, batch_sources, batch_meta, vectors
            ):
                payload = {**meta, "source": src, "text": doc, "chunk_id": chunk_id}
                points.append(
                    PointStruct(id=_point_id(chunk_id), vector=vec, payload=payload)
                )
            self._client.upsert(collection_name=self._collection, points=points)
            total += len(batch_chunks)
        log.info("vector.qdrant.add", count=total, batch_size=batch_size)
        return total

    def query(
        self,
        text: str,
        k: int = 4,
        *,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.count() == 0:
            return []
        qvec = embed_documents([text])[0]
        flt = _qdrant_filter(metadata_filter)
        hits = self._client.query_points(
            collection_name=self._collection,
            query=qvec,
            limit=k,
            query_filter=flt,
            with_payload=True,
        ).points
        out: list[dict[str, Any]] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            doc = str(payload.pop("text", ""))
            chunk_id = str(payload.pop("chunk_id", hit.id))
            score = float(hit.score or 0.0)
            out.append(chunk_from_hit(payload, text=doc, doc_id=chunk_id, score=score))
        return out

    def count(self) -> int:
        try:
            return int(self._client.count(collection_name=self._collection, exact=True).count)
        except Exception:
            return 0

    def scroll_records(self) -> list[dict[str, Any]]:
        if self.count() == 0:
            return []
        out: list[dict[str, Any]] = []
        offset = None
        while True:
            records, offset = self._client.scroll(
                collection_name=self._collection,
                with_payload=True,
                with_vectors=False,
                limit=256,
                offset=offset,
            )
            for rec in records:
                payload = dict(rec.payload or {})
                doc = str(payload.pop("text", ""))
                chunk_id = str(payload.pop("chunk_id", rec.id))
                out.append(chunk_from_hit(payload, text=doc, doc_id=chunk_id, score=0.0))
            if offset is None:
                break
        return out

    def list_doc_fingerprints(self) -> dict[str, tuple[str, str]]:
        """从 Qdrant 里扫出「已经入库的文档指纹」，给 _sync_kb 对照用。"""
        if self.count() == 0:
            return {}
        out: dict[str, tuple[str, str]] = {}
        offset = None
        while True:
            records, offset = self._client.scroll(
                collection_name=self._collection,
                with_payload=["doc_id", "file_hash", "corpus"],
                with_vectors=False,
                limit=256,
                offset=offset,
            )
            for rec in records:
                payload = rec.payload or {}
                doc_id = str(payload.get("doc_id") or "")
                if not doc_id:
                    continue
                out[doc_id] = (
                    str(payload.get("file_hash") or ""),
                    str(payload.get("corpus") or ""),
                )
            if offset is None:
                break
        return out

    def delete_by_doc_ids(self, doc_ids: list[str]) -> int:
        ids = [d for d in doc_ids if d]
        if not ids or self.count() == 0:
            return 0
        before = self.count()
        self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchAny(any=ids))]
                )
            ),
        )
        return max(0, before - self.count())

    def purge_unfingerprinted(self) -> int:
        if self.count() == 0:
            return 0
        before = self.count()
        self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[IsEmptyCondition(is_empty=PayloadField(key="doc_id"))]
                )
            ),
        )
        removed = max(0, before - self.count())
        if removed:
            log.info("vector.qdrant.purge_unfingerprinted", count=removed)
        return removed
