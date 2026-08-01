"""检索过滤：元数据匹配 / Chroma where 构造 + 检索后低分丢弃。

`metadata_filter` 在向量与 BM25 **召回阶段**下推（Chroma `where` / BM25 子集打分）；
`filter_chunks` 仍保留元数据校验与 rerank 低分过滤。
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..logging import get_logger

log = get_logger(__name__)


def chroma_where(metadata_filter: dict[str, str]) -> dict[str, Any] | None:
    """将 metadata_filter 转为 Chroma collection.query(where=...) 子句。

    仅支持等值匹配；`source_contains` 无法下推，留待 filter_chunks 处理。
    """
    exact = {k: v for k, v in metadata_filter.items() if k != "source_contains"}
    if not exact:
        return None
    if len(exact) == 1:
        key, value = next(iter(exact.items()))
        return {key: value}
    return {"$and": [{key: value} for key, value in exact.items()]}


def match_metadata(chunk: dict[str, Any], flt: dict[str, str]) -> bool:
    """chunk 或入库 metadatas 字典是否满足过滤条件。"""
    return _match_metadata(chunk, flt)


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
    """按分数与元数据过滤（元数据召回阶段已下推时此处为二次校验）。

    RRF / 向量未 rerank 时不做分数字段过滤。
    """
    if not chunks:
        return []
    # 初始化一个空列表，用于存储过滤后的结果
    out = list(chunks)
    # 初始化一个空字典，用于存储元数据过滤条件
    meta = metadata_filter or {}
    # 如果元数据过滤条件不为空，则进行元数据过滤
    if meta:
        # 记录过滤前的结果数量
        before = len(out)
        # 对每个结果进行元数据过滤
        out = [c for c in out if _match_metadata(c, meta)]
        log.info("filter.metadata", before=before, after=len(out), filter=meta)

    # 如果启用重排，则进行分数过滤
    if rerank_was_used:
        # 获取分数阈值
        threshold = (
            min_score
            if min_score is not None
            else get_settings().refuse_min_rerank_score
        )
        # 记录过滤前的结果数量
        before = len(out)
        # 对每个结果进行分数过滤
        out = [c for c in out if float(c.get("score", 0)) >= threshold]
        if before != len(out):
            log.info("filter.score", before=before, after=len(out), min_score=threshold)

    return out
