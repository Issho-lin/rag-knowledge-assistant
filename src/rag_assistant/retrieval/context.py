"""父文档检索：子块命中时扩展为所属节全文。

与按标题切块配合：过长节被 _pack_paragraphs 拆开后，parent_text 保留整节。
通讯录等短块 KB 可在 Profile 关闭此能力。
"""

from __future__ import annotations

from typing import Any

from ..logging import get_logger

log = get_logger(__name__)


def expand_parent_context(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将子块 text 替换为 parent_text（去重）；无 parent 则原样保留。"""
    if not chunks:
        return []

    seen_parent: set[str] = set()
    out: list[dict[str, Any]] = []

    for chunk in chunks:
        parent = str(chunk.get("parent_text") or "").strip()
        if not parent or parent == chunk.get("text", "").strip():
            out.append(chunk)
            continue
        if parent in seen_parent:
            continue
        row = dict(chunk)
        row["text"] = parent
        row["expanded_from_child"] = True
        out.append(row)
        seen_parent.add(parent)

    if len(out) < len(chunks):
        log.info(
            "context.parent_expand",
            in_count=len(chunks),
            out_count=len(out),
        )
    return out
