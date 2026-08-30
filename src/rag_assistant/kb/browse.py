"""已入库文档 / 切片浏览（运营侧 inspect）。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.logging import get_logger
from ..ingest.uploads import allowed_suffixes
from ..kb.registry import get_kb, list_kbs
from ..retrieval.vector_store import create_vector_store

log = get_logger(__name__)


def _records_for_kb(kb_id: str) -> list[dict[str, Any]]:
    kb = get_kb(kb_id)
    try:
        if kb.backend != "vector":
            return _graph_file_records()
        return create_vector_store(kb_id=kb_id).scroll_records()
    except Exception as exc:
        log.warning("browse.unavailable", kb=kb_id, error=str(exc))
        return []


def _graph_file_records() -> list[dict[str, Any]]:
    """图谱没有文本 chunk；用源 Markdown 列表让运营能看见已接入的关系语料。"""
    root = get_settings().corpus_dir / "kb_graph" / "markdown"
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        out.append(
            {
                "id": f"graph:{path.name}",
                "text": text[:4000],
                "source": str(path),
                "kb": "relations",
                "kind": "markdown",
                "chunk_index": 0,
            }
        )
    return out


def kb_summaries() -> list[dict[str, Any]]:
    rows = []
    for kb in list_kbs():
        records = _records_for_kb(kb.id)
        sources = {str(r.get("source") or "") for r in records if r.get("source")}
        rows.append(
            {
                "id": kb.id,
                "name": kb.name,
                "tool_name": kb.tool_name,
                "backend": kb.backend,
                "chunk_count": len(records),
                "document_count": len(sources),
                "allowed_suffixes": list(allowed_suffixes(kb.id)),
            }
        )
    return rows


def list_documents(kb_id: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in _records_for_kb(kb_id):
        src = str(rec.get("source") or "")
        grouped[src].append(rec)
    docs = []
    for source, chunks in sorted(grouped.items()):
        docs.append(
            {
                "source": source,
                "filename": Path(source).name,
                "chunk_count": len(chunks),
                "kind": str(chunks[0].get("kind") or ""),
                "doc_id": str(chunks[0].get("doc_id") or ""),
            }
        )
    return docs


def list_chunks(
    kb_id: str,
    *,
    source: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    records = _records_for_kb(kb_id)
    if source:
        records = [r for r in records if str(r.get("source") or "") == source]
    needle = (q or "").strip().lower()
    if needle:
        records = [r for r in records if needle in str(r.get("text") or "").lower()]
    total = len(records)
    page = records[offset : offset + max(1, min(limit, 200))]
    items = []
    for r in page:
        text = str(r.get("text") or "")
        items.append(
            {
                "id": r.get("id"),
                "source": r.get("source"),
                "filename": Path(str(r.get("source") or "")).name,
                "chunk_index": r.get("chunk_index"),
                "kind": r.get("kind"),
                "chars": len(text),
                "text": text,
            }
        )
    return {"total": total, "offset": offset, "limit": limit, "items": items}
