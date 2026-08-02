"""全库 / 指定 KB 问答（--query，默认模式）。"""

from __future__ import annotations

from pathlib import Path

from ...core.config import get_settings
from ...conversation import ChatTurn
from ...answer import build_citations, produce_answer
from ...core.observability import flush_langfuse, get_langfuse
from ..helpers import ensure_store_ready
from ..preprocess.rewrite import rewrite_for_retrieval
from ..result import QueryResult
from ..retrieve import retrieve_chunks


def query(
    q: str,
    k: int = 4,
    *,
    history: list[ChatTurn] | None = None,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
    kb_id: str | None = None,
) -> QueryResult:
    """检索统一知识库并生成回答；若配置了 Langfuse，整条链路写入一条 trace。"""
    if (empty := ensure_store_ready()) is not None:
        return empty

    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank
    search_q = rewrite_for_retrieval(q, history)

    def _run_retrieve() -> list[dict]:
        return retrieve_chunks(
            search_q, k=k, retrieve=retrieve, use_rerank=do_rerank, kb_id=kb_id
        )

    def _finish(chunks: list[dict]) -> QueryResult:
        answer, refused, reason = produce_answer(search_q, chunks, use_rerank=do_rerank)
        return QueryResult(
            answer=answer,
            chunks=chunks,
            citations=build_citations(chunks, answer),
            refused=refused,
            refusal_reason=reason,
            rewritten_query=search_q if search_q != q.strip() else None,
        )

    lf = get_langfuse()
    if lf is None:
        return _finish(_run_retrieve())

    retrieve_mode = retrieve if retrieve in {"hybrid", "vector"} else "hybrid"
    try:
        with lf.start_as_current_observation(
            name="rag-query",
            as_type="chain",
            input={
                "query": q,
                "rewritten_query": search_q,
                "k": k,
                "retrieve": retrieve_mode,
                "rerank": do_rerank,
                "kb_id": kb_id,
                "history_turns": len(history or []),
            },
        ) as root:
            with lf.start_as_current_observation(
                name="retrieve",
                as_type="retriever",
                input={
                    "query": search_q,
                    "k": k,
                    "mode": retrieve_mode,
                    "rerank": do_rerank,
                },
            ) as ret:
                chunks = _run_retrieve()
                ret.update(
                    output=[
                        {
                            "source": Path(c["source"]).name,
                            "score": round(c["score"], 4),
                            "preview": c["text"].replace("\n", " ")[:200],
                        }
                        for c in chunks
                    ]
                )
            result = _finish(chunks)
            root.update(
                output={
                    "answer": result.answer,
                    "rewritten_query": result.rewritten_query,
                    "citations": [c.to_dict() for c in result.citations],
                    "refused": result.refused,
                    "refusal_reason": (
                        result.refusal_reason.value if result.refusal_reason else None
                    ),
                }
            )
        return result
    finally:
        flush_langfuse()
