"""OpenSearch BM25 关键词检索（Phase 2 生产默认）。"""

from __future__ import annotations

from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk

from ..core.config import get_settings
from ..core.logging import get_logger
from .metadata import chunk_from_hit

log = get_logger(__name__)

_INDEX_BODY: dict[str, Any] = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "text": {"type": "text"},
            "source": {"type": "keyword"},
            "kind": {"type": "keyword"},
            "corpus": {"type": "keyword"},
            "kb": {"type": "keyword"},
            "domain": {"type": "keyword"},
            "parent_text": {"type": "text", "index": False},
            "chunk_index": {"type": "integer"},
        }
    },
}


def _build_client(url: str) -> OpenSearch:
    return OpenSearch(
        hosts=[url],
        use_ssl=url.startswith("https"),
        verify_certs=False,
        ssl_show_warn=False,
    )


def _filter_clauses(metadata_filter: dict[str, str] | None) -> list[dict[str, Any]]:
    if not metadata_filter:
        return []
    return [{"term": {key: value}} for key, value in metadata_filter.items()]


class OpenSearchBM25Store:
    def __init__(self) -> None:
        s = get_settings()
        self._index = s.opensearch_index
        self._client = _build_client(s.opensearch_url)

    def delete_index(self) -> None:
        if self._client.indices.exists(index=self._index):
            self._client.indices.delete(index=self._index)
            log.info("bm25.opensearch.index_deleted", index=self._index)

    def _ensure_index(self) -> None:
        if not self._client.indices.exists(index=self._index):
            self._client.indices.create(index=self._index, body=_INDEX_BODY)
            log.info("bm25.opensearch.index_created", index=self._index)

    def rebuild(
        self,
        ids: list[str],
        docs: list[str],
        sources: list[str],
        *,
        metadatas: list[dict[str, str | int]] | None = None,
    ) -> int:
        if not (len(ids) == len(docs) == len(sources)):
            raise ValueError("ids/docs/sources 长度必须一致")
        if metadatas is not None and len(metadatas) != len(docs):
            raise ValueError("metadatas 长度必须与 docs 一致")

        self.delete_index()
        self._ensure_index()

        if not docs:
            return 0

        actions: list[dict[str, Any]] = []
        for i, (chunk_id, doc, src) in enumerate(zip(ids, docs, sources)):
            meta = (
                metadatas[i]
                if metadatas is not None
                else {"source": src}
            )
            source_doc: dict[str, Any] = {
                "chunk_id": chunk_id,
                "text": doc,
                "source": src,
                **meta,
            }
            actions.append(
                {
                    "_index": self._index,
                    "_id": chunk_id,
                    "_source": source_doc,
                }
            )

        bulk(self._client, actions, refresh=True)
        log.info("bm25.opensearch.rebuilt", index=self._index, count=len(docs))
        return len(docs)

    def query(
        self,
        text: str,
        k: int = 4,
        *,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.count() == 0:
            return []
        stripped = text.strip()
        if not stripped:
            return []

        bool_query: dict[str, Any] = {
            "must": [{"match": {"text": {"query": stripped}}}],
        }
        filters = _filter_clauses(metadata_filter)
        if filters:
            bool_query["filter"] = filters

        body = {
            "size": k,
            "query": {"bool": bool_query},
        }
        res = self._client.search(index=self._index, body=body)
        hits = res.get("hits", {}).get("hits", [])
        out: list[dict[str, Any]] = []
        for hit in hits:
            src = dict(hit.get("_source", {}))
            doc = str(src.pop("text", ""))
            chunk_id = str(src.pop("chunk_id", hit.get("_id", "")))
            score = float(hit.get("_score", 0.0))
            out.append(chunk_from_hit(src, text=doc, doc_id=chunk_id, score=score))
        return out

    def count(self) -> int:
        if not self._client.indices.exists(index=self._index):
            return 0
        try:
            return int(self._client.count(index=self._index).get("count", 0))
        except Exception:
            return 0
