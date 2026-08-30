"""入库前切片预览：解析 + Profile 切块，不写向量。"""

from __future__ import annotations

from pathlib import Path

from ..kb import get_kb
from .chunking import chunk_document
from .loaders import load_file


def preview_path(path: Path, *, kb_id: str) -> dict:
    kb = get_kb(kb_id)
    doc = load_file(path)
    infos = chunk_document(doc, kb.profile.max_chars, kb.profile.chunk_strategy)
    return {
        "filename": path.name,
        "source": str(path),
        "kind": doc.metadata.get("kind", ""),
        "chars": len(doc.text),
        "strategy": kb.profile.chunk_strategy,
        "max_chars": kb.profile.max_chars,
        "empty": not bool(doc.text.strip()),
        "chunks": [
            {"index": info.chunk_index, "chars": len(info.text), "text": info.text}
            for info in infos
        ],
    }
