"""检索后过滤：低相关丢弃 + 元数据过滤。

各 KB Profile 可覆盖阈值或追加 domain 约束。
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..logging import get_logger

log = get_logger(__name__)


def _match_metadata(chunk: dict[str, Any], flt: dict[str, str]) -> bool:
    """全部键值匹配才保留；source_contains 为子串匹配。"""
    for key, expected in flt.items():
        if key == "source_contains":
            if expected not in chunk.get("source", ""):
                return False
            continue
        if str(chunk.get(key, "")) != expected:
            return False
    return True


def filter_chunks(
    chunks: list[dict[str, Any]],
    *,
    min_score: float | None = None,
    metadata_filter: dict[str, str] | None = None,
    rerank_was_used: bool = False,
) -> list[dict[str, Any]]:
    """按分数与元数据过滤；RRF 未重排时跳过分数字段。"""
    if not chunks:
        return []

    out = list(chunks)
    meta = metadata_filter or {}

    if meta:
        before = len(out)
        out = [c for c in out if _match_metadata(c, meta)]
        log.info("filter.metadata", before=before, after=len(out), filter=meta)

    if rerank_was_used:
        threshold = min_score
        if threshold is None:
            threshold = get_settings().retrieval_min_score
        before = len(out)
        out = [c for c in out if float(c.get("score", 0)) >= threshold]
        if before != len(out):
            log.info("filter.score", before=before, after=len(out), min_score=threshold)

    return out
