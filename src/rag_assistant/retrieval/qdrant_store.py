"""Qdrant 向量库（生产默认）。"""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
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
            return
        dim = embedding_dimension()
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        log.info("vector.qdrant.collection_created", name=self._collection, dim=dim)

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
