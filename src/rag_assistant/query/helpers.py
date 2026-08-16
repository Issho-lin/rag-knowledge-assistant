"""问答模式共用的辅助函数（含 ReAct 入口前的向量库校验）。"""

from __future__ import annotations

from ..core.logging import get_logger
from ..kb.storage import total_vector_count
from .result import QueryResult

log = get_logger(__name__)

EMPTY_STORE_MSG = "知识库为空。请先执行：python -m rag_assistant.pipeline --ingest --reset"


def empty_store_result() -> QueryResult:
    return QueryResult(answer=EMPTY_STORE_MSG, chunks=[], citations=[], refused=True)


def ensure_store_ready() -> QueryResult | None:
    """向量库为空时返回拒答结果，否则返回 None 表示可继续 ReAct / query。"""
    if total_vector_count() == 0:
        log.error("query.empty_store", hint="run --ingest first")
        return empty_store_result()
    return None
