"""检索入口：ReAct 工具经 ``run_kb_retrieve`` 调用，与 CLI / eval 共用同一检索链。"""

from __future__ import annotations

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from ..core.paths import BM25_PATH, UNIFIED_CHROMA
from ..retrieval.engine import retrieve_with_options
from ..retrieval.options import RetrievalOptions
from ..retrieval.vector import VectorStore

log = get_logger(__name__)


def merge_retrieval_options(
    options: RetrievalOptions | None,
    kb_id: str | None,
) -> RetrievalOptions:
    """合并全局与 KB Profile 的检索选项；指定 kb_id 时追加 metadata_filter 限定单库。"""
    if kb_id is None:
        return options or RetrievalOptions.from_settings()
    from ..kb import get_kb

    kb_opts = get_kb(kb_id).profile.retrieval
    meta = {"kb": kb_id, **kb_opts.metadata_filter}
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
) -> list[dict]:
    """先多召回，可选重排、过滤、父文档扩展。"""
    return retrieve_with_options(
        q,
        k,
        mode,
        do_rerank=do_rerank,
        options=options,
        chroma_path=UNIFIED_CHROMA,
        bm25_path=BM25_PATH,
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

    ReAct 路径：由 ``run_kb_retrieve`` 传入 ``kb_id``，走对应 Profile（切块策略、父文档扩展等）。
    """
    configure_logging()
    store = VectorStore(chroma_path=UNIFIED_CHROMA)
    if store.count() == 0:
        log.error("retrieve.empty_store", hint="run --ingest first")
        return []

    mode = _normalize_retrieve_mode(retrieve)
    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank
    # kb_id 决定 metadata_filter={"kb": ...} 与各库 Profile
    opts = merge_retrieval_options(options, kb_id)
    chunks = _retrieve_and_maybe_rerank(q, k, mode, do_rerank=do_rerank, options=opts)
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
