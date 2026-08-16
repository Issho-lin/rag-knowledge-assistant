"""检索入口：ReAct 工具经 ``run_kb_retrieve`` 调用，与 CLI / eval 共用同一检索链。"""

from __future__ import annotations

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from ..kb.storage import total_vector_count
from ..retrieval.engine import retrieve_with_options
from ..retrieval.options import RetrievalOptions

log = get_logger(__name__)


def merge_retrieval_options(
    options: RetrievalOptions | None,
    kb_id: str | None,
) -> RetrievalOptions:
    """合并全局与 KB Profile；物理分库下不再用 metadata_filter 限定 kb。"""
    if kb_id is None:
        return options or RetrievalOptions.from_settings()
    from ..kb import get_kb

    kb_opts = get_kb(kb_id).profile.retrieval
    meta = dict(kb_opts.metadata_filter)
    if options and options.metadata_filter:
        meta.update(options.metadata_filter)
    return RetrievalOptions(
        decompose=kb_opts.decompose,
        expand_parent=kb_opts.expand_parent,
        metadata_filter=meta,
    )


def _normalize_retrieve_mode(retrieve: str) -> str:
    return retrieve if retrieve in {"hybrid", "vector"} else "hybrid"


def _retrieve_and_maybe_rerank(
    q: str,
    k: int,
    mode: str,
    *,
    do_rerank: bool,
    options: RetrievalOptions | None = None,
    kb_id: str | None = None,
) -> list[dict]:
    """先多召回，可选重排、过滤、父文档扩展。"""
    return retrieve_with_options(
        q,
        k,
        mode,
        do_rerank=do_rerank,
        options=options,
        kb_id=kb_id,
    )


def retrieve_chunks(
    q: str,
    k: int = 4,
    *,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
    options: RetrievalOptions | None = None,
    kb_id: str | None = None,
) -> list[dict]:
    """仅检索，返回 top-k chunks。

    ReAct 路径：由 ``run_kb_retrieve`` 传入 ``kb_id``，走对应物理索引与 Profile。
    """
    configure_logging()
    if total_vector_count() == 0:
        log.error("retrieve.empty_store", hint="run --ingest first")
        return []

    mode = _normalize_retrieve_mode(retrieve)
    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank
    opts = merge_retrieval_options(options, kb_id)
    chunks = _retrieve_and_maybe_rerank(
        q, k, mode, do_rerank=do_rerank, options=opts, kb_id=kb_id
    )
    log.info(
        "retrieve.done",
        mode=mode,
        rerank=do_rerank,
        k=k,
        kb_id=kb_id,
        filter=do_rerank,
        decompose=opts.decompose,
        parent_expand=opts.expand_parent,
        top_score=chunks[0]["score"] if chunks else None,
    )
    return chunks
