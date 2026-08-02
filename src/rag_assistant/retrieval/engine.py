"""检索编排：ReAct 工具经 retrieve_chunks → retrieve_with_options 进入此流水线。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..core.config import get_settings
from ..core.logging import get_logger
from ..query.preprocess.decompose import decompose_for_retrieval
from .bm25 import BM25Store
from .context import expand_parent_context
from .filters import filter_chunks
from .hybrid import HybridRetriever, rrf_fuse
from .options import RetrievalOptions
from .rerank import rerank
from .vector import VectorStore

log = get_logger(__name__)

RetrieveFn = Callable[[str, int, str], list[dict[str, Any]]]


def _base_retrieve(
    q: str,
    k: int,
    mode: str,
    *,
    chroma_path: Path,
    bm25_path: Path,
    metadata_filter: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """基础检索：向量化检索或 BM25 检索（metadata_filter 在召回阶段下推）。"""
    meta = metadata_filter or None
    store = VectorStore(chroma_path=chroma_path)
    if mode == "vector":
        return store.query(q, k=k, metadata_filter=meta)
    bm25 = BM25Store(bm25_path)
    if bm25.count() == 0:
        log.warning("retrieve.bm25_empty", hint="run --ingest --reset; fallback to vector")
        return store.query(q, k=k, metadata_filter=meta)
    return HybridRetriever(store, bm25).query(q, k=k, metadata_filter=meta)


def retrieve_with_options(
    q: str,
    k: int,
    mode: str,
    *,
    do_rerank: bool,
    options: RetrievalOptions | None = None,
    chroma_path: Path,
    bm25_path: Path,
) -> list[dict[str, Any]]:
    """统一检索入口：子查询分解 → 召回 → 重排 → 过滤 → 父文档扩展。

    ReAct 每次工具调用都会走完整链路；metadata_filter 来自 KB Profile（限定单库）。
    """

    # 获取检索选项
    opts = options or RetrievalOptions.from_settings()
    # 重排前多召回候选，再 rerank 截断，提高 top-k 质量
    candidate_k = max(k * 3, 12) if do_rerank else k

    meta_filter = dict(opts.metadata_filter) if opts.metadata_filter else None

    sub_queries = decompose_for_retrieval(q) if opts.decompose else [q]
    if len(sub_queries) > 1:
        ranked_lists: list[list[dict[str, Any]]] = []
        for sq in sub_queries:
            ranked_lists.append(
                _base_retrieve(
                    sq,
                    candidate_k,
                    mode,
                    chroma_path=chroma_path,
                    bm25_path=bm25_path,
                    metadata_filter=meta_filter,
                )
            )
        candidates = rrf_fuse(ranked_lists, k=candidate_k)
        log.info("retrieve.decomposed", subqueries=sub_queries, fused=len(candidates))
    else:
        candidates = _base_retrieve(
            sub_queries[0],
            candidate_k,
            mode,
            chroma_path=chroma_path,
            bm25_path=bm25_path,
            metadata_filter=meta_filter,
        )
    # 如果启用重排，则对候选结果进行重排（根据问题和结果相关性重排）
    if do_rerank and candidates:
        candidates = rerank(q, candidates, top_k=candidate_k)

    if candidates:
        # 对候选结果进行元数据 / 分数过滤
        candidates = filter_chunks(
            candidates,
            metadata_filter=opts.metadata_filter or None,
            rerank_was_used=do_rerank,
        )

    # 截取 top_k 条结果
    chunks = candidates[:k]

    # 如果启用父文档扩展，则扩展父文档上下文
    if opts.expand_parent:
        chunks = expand_parent_context(chunks)

    return chunks
