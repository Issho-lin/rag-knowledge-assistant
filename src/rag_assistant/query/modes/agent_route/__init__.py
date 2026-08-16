"""--agent：function calling 选型 + 单库 RAG。"""

from __future__ import annotations

from ....core.config import get_settings
from ....conversation import ChatTurn
from ....answer import build_citations, produce_answer
from ....kb.search import run_kb_retrieve
from ....core.logging import get_logger
from ....core.observability import flush_langfuse, get_langfuse
from ...helpers import ensure_store_ready
from ...preprocess.rewrite import rewrite_for_retrieval
from ...result import QueryResult
from ..direct import query
from .select import resolve_tool_to_kb_id, select_tool_names

log = get_logger(__name__)

__all__ = ["query_agent", "resolve_tool_to_kb_id", "select_tool_names"]


def query_agent(
    q: str,
    k: int = 4,
    *,
    history: list[ChatTurn] | None = None,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
) -> QueryResult:
    """Agent 路由：LLM 选 KB 工具 → 在该库内 RAG；无工具选中时回退全库 query。"""
    if (empty := ensure_store_ready()) is not None:
        return empty

    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank
    search_q = rewrite_for_retrieval(q, history)

    def _route() -> tuple[str, str]:
        tool_names = select_tool_names(search_q)
        if not tool_names:
            log.warning("agent.fallback_full_corpus", query=search_q[:80])
            return "", ""
        tool = tool_names[0]
        return tool, resolve_tool_to_kb_id(tool)

    def _run_kb(kb_id: str) -> QueryResult:
        retrieved = run_kb_retrieve(
            kb_id,
            search_q,
            k=k,
            retrieve=retrieve,
            use_rerank=do_rerank,
        )
        answer, refused, reason = produce_answer(
            search_q, retrieved.chunks, use_rerank=do_rerank
        )
        return QueryResult(
            answer=answer,
            chunks=retrieved.chunks,
            citations=build_citations(retrieved.chunks, answer),
            refused=refused,
            refusal_reason=reason,
            rewritten_query=search_q if search_q != q.strip() else None,
            routed_tool=retrieved.tool_name,
            routed_kb_id=kb_id,
        )

    lf = get_langfuse()
    if lf is None:
        tool_name, kb_id = _route()
        if not kb_id:
            return query(
                q,
                k=k,
                history=history,
                retrieve=retrieve,
                use_rerank=use_rerank,
            )
        return _run_kb(kb_id)

    try:
        with lf.start_as_current_observation(
            name="rag-agent-query",
            as_type="chain",
            input={"query": q, "rewritten_query": search_q},
        ) as root:
            with lf.start_as_current_observation(
                name="agent-route",
                as_type="agent",
                input={"query": search_q},
            ) as route_span:
                tool_name, kb_id = _route()
                route_span.update(
                    output={"tool_name": tool_name or None, "kb_id": kb_id or None}
                )
            if not kb_id:
                result = query(
                    q,
                    k=k,
                    history=history,
                    retrieve=retrieve,
                    use_rerank=use_rerank,
                )
            else:
                result = _run_kb(kb_id)
            root.update(
                output={
                    "answer": result.answer,
                    "routed_tool": result.routed_tool,
                    "routed_kb_id": result.routed_kb_id,
                    "refused": result.refused,
                }
            )
        return result
    finally:
        flush_langfuse()
