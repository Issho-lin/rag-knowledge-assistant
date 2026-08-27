"""检索编排：ReAct 工具经 retrieve_chunks → retrieve_with_options 进入此流水线。"""

from __future__ import annotations

from typing import Any, Callable

from ..core.config import get_settings
from ..core.logging import get_logger
from ..kb.registry import list_vector_kbs
from ..query.preprocess.decompose import decompose_for_retrieval
from .bm25_store import create_bm25_store
from .context import expand_parent_context
from .filters import filter_chunks
from .hybrid import HybridRetriever, rrf_fuse
from .options import RetrievalOptions
from .rerank import rerank
from .vector_store import create_vector_store

log = get_logger(__name__)

RetrieveFn = Callable[[str, int, str], list[dict[str, Any]]]


def _base_retrieve(
    q: str,
    k: int,
    mode: str,
    *,
    kb_id: str | None = None,
    metadata_filter: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """基础检索：物理分库直连对应 store；metadata_filter 仅用于 profile 内非 kb 字段。"""
    meta = metadata_filter or None
    store = create_vector_store(kb_id=kb_id)
    if mode == "vector":
        return store.query(q, k=k, metadata_filter=meta)
    bm25 = create_bm25_store(kb_id=kb_id)
    if bm25.count() == 0:
        log.warning("retrieve.bm25_empty", kb_id=kb_id, hint="run --ingest --reset; fallback to vector")
        return store.query(q, k=k, metadata_filter=meta)
    return HybridRetriever(store, bm25).query(q, k=k, metadata_filter=meta)


def _retrieve_one_query(
    q: str,
    k: int,
    mode: str,
    *,
    kb_id: str | None,
    metadata_filter: dict[str, str] | None,
) -> list[dict[str, Any]]:
    """单条 query：指定 kb_id 查单库；否则跨库 RRF。"""
    if kb_id is not None:
        return _base_retrieve(
            q,
            k,
            mode,
            kb_id=kb_id,
            metadata_filter=metadata_filter,
        )
    per_kb = [
        _base_retrieve(
            q,
            k,
            mode,
            kb_id=kb.id,
            metadata_filter=metadata_filter,
        )
        for kb in list_vector_kbs()
    ]
    return rrf_fuse(per_kb, k=k)


def retrieve_with_options(
    q: str,
    k: int,
    mode: str,
    *,
    do_rerank: bool,
    options: RetrievalOptions | None = None,
    kb_id: str | None = None,
) -> list[dict[str, Any]]:
    """统一检索入口：子查询分解 → 召回 → 重排 → 过滤 → 父文档扩展。

    物理分库：kb_id 决定直连哪套索引；跨库时对各 KB RRF 融合。
    """

    opts = options or RetrievalOptions.from_settings()
    candidate_k = max(k * 3, 12) if do_rerank else k

    meta_filter = dict(opts.metadata_filter) if opts.metadata_filter else None

    sub_queries = decompose_for_retrieval(q) if opts.decompose else [q]
    if len(sub_queries) > 1:
        ranked_lists: list[list[dict[str, Any]]] = []
        for sq in sub_queries:
            ranked_lists.append(
                _retrieve_one_query(
                    sq,
                    candidate_k,
                    mode,
                    kb_id=kb_id,
                    metadata_filter=meta_filter,
                )
            )
        candidates = rrf_fuse(ranked_lists, k=candidate_k)
        log.info("retrieve.decomposed", subqueries=sub_queries, fused=len(candidates))
    else:
        candidates = _retrieve_one_query(
            sub_queries[0],
            candidate_k,
            mode,
            kb_id=kb_id,
            metadata_filter=meta_filter,
        )

    if do_rerank and candidates:
        candidates = rerank(q, candidates, top_k=candidate_k)

    if candidates:
        candidates = filter_chunks(
            candidates,
            metadata_filter=opts.metadata_filter or None,
            rerank_was_used=do_rerank,
        )

    chunks = candidates[:k]

    if opts.crag_enabled:
        from ..core.config import get_settings
        from .crag import maybe_apply_crag

        # Profile 声明能力；CRAG_ENABLED=false 为全局 kill switch
        if get_settings().crag_enabled:

            def _again(new_q: str) -> list[dict[str, Any]]:
                again_opts = opts.with_overrides(crag_enabled=False)
                return retrieve_with_options(
                    new_q,
                    k,
                    mode,
                    do_rerank=do_rerank,
                    options=again_opts,
                    kb_id=kb_id,
                )

            chunks = maybe_apply_crag(
                q,
                chunks,
                retrieve_again=_again,
                enabled=True,
            )

    if opts.expand_parent:
        chunks = expand_parent_context(chunks)

    return chunks
