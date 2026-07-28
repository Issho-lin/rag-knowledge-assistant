"""端到端 RAG 流水线：入库 → 检索 → 生成。

产品语义（智能客服）：用户只提问，系统检索全部已入库知识，不选库。

    uv run python -m rag_assistant.pipeline --ingest --reset
    uv run python -m rag_assistant.pipeline --query "年假怎么算"

新增知识：把文件放进 data/corpus/<任意名>/{markdown,html,csv}/，再执行一次 --ingest --reset。

建库与问答分开：入库贵且慢；问答只嵌问题向量。
默认：向量+BM25 混合（RRF）+ 重排；可用 --retrieve / --no-rerank 做对照。

流程：
1. 用户发起问题
2. 多路检索（向量检索+BM25关键词检索）
3. 两路检索各自排名（向量检索是自动排名，BM25是根据分数排名）
4. rrf融合检索（两路检索综合排名靠前的，top_k的3倍，至少12条）
5. 重排（问题和检索结果的相关性评分排名取top_k）
6. 模型生成回答
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from .config import get_settings
from .generation import generate
from .ingest.chunking import chunk_by_heading
from .ingest.loaders import Document, load_corpus
from .logging import configure_logging, get_logger
from .observability import flush_langfuse, get_langfuse
from .retrieval.bm25 import BM25Store
from .retrieval.hybrid import HybridRetriever
from .retrieval.rerank import rerank
from .retrieval.vector import VectorStore

from colorama import Fore

log = get_logger(__name__)

# 统一向量库（客服只查这一个库）；语料父目录见配置 CORPUS_DIR
_UNIFIED_CHROMA = Path("data/chroma/unified")
_BM25_PATH = _UNIFIED_CHROMA / "bm25.pkl"


def _chunk_id(source: str, text: str, index: int) -> str:
    """稳定 id：同源同序同内容则不变，便于向量与 BM25 对齐。"""
    digest = hashlib.sha1(f"{source}\0{index}\0{text}".encode("utf-8")).hexdigest()[:16]
    return f"c_{digest}"


def discover_corpus_roots(parent: Path | None = None) -> list[Path]:
    """发现父目录下所有合法语料包（子目录内存在 markdown/ 或 html/ 或 csv/）。"""
    parent = parent or get_settings().corpus_dir
    if not parent.is_dir():
        return []

    roots: list[Path] = []
    for child in sorted(parent.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if any((child / sub).is_dir() for sub in ("markdown", "html", "csv", "pdf")):
            roots.append(child)
    return roots


def load_all_documents(only: str | None = None) -> list[Document]:
    """加载全部语料包；only 为目录名时仅加载那一包（运维调试用）。"""
    roots = discover_corpus_roots()
    if only:
        roots = [r for r in roots if r.name == only]
        if not roots:
            raise FileNotFoundError(
                f"未找到语料包 {only!r}。当前可用: {[r.name for r in discover_corpus_roots()]}"
            )

    docs: list[Document] = []
    for root in roots:
        part = load_corpus(root)
        for d in part:
            d.metadata.setdefault("corpus", root.name)
        docs.extend(part)
        log.info("ingest.load_bundle", corpus=root.name, docs=len(part))
    return docs


def ingest(*, reset: bool = False, only: str | None = None) -> int:
    """将知识库全部（或指定包）切块入库：向量库 + BM25。"""
    configure_logging()
    docs = load_all_documents(only=only)
    if not docs:
        log.error("ingest.empty", parent=str(get_settings().corpus_dir))
        print("未找到任何语料。请在 data/corpus/<名称>/{markdown,html,csv}/ 下放置文件。")
        return 0

    chroma_path = _UNIFIED_CHROMA
    if reset and chroma_path.exists():
        shutil.rmtree(chroma_path)
        log.info("ingest.reset_store", path=str(chroma_path))

    all_ids: list[str] = []
    all_chunks: list[str] = []
    all_sources: list[str] = []
    for d in docs:
        chunks = chunk_by_heading(d)
        for i, chunk in enumerate(chunks):
            all_ids.append(_chunk_id(d.source, chunk, i))
            all_chunks.append(chunk)
            all_sources.append(d.source)

    if not all_chunks:
        print("切块结果为空，未写入索引。")
        return 0

    store = VectorStore(chroma_path=chroma_path)
    total = store.add(all_chunks, all_sources, ids=all_ids)
    bm25 = BM25Store(_BM25_PATH)
    bm25.rebuild(all_ids, all_chunks, all_sources)

    bundles = sorted({d.metadata.get("corpus", "?") for d in docs})
    log.info(
        "ingest.done",
        bundles=bundles,
        docs=len(docs),
        chunks=total,
        store_count=store.count(),
        bm25_count=bm25.count(),
        chroma=str(chroma_path),
    )
    print(f"\n已索引 {total} 个 chunk，来源语料包: {', '.join(bundles)}")
    print(f"统一向量库: {chroma_path}")
    print(f"BM25 索引: {_BM25_PATH}")
    return total


def _retrieve(q: str, k: int, mode: str) -> list[dict]:
    """召回 k 条；mode=hybrid|vector。"""
    store = VectorStore(chroma_path=_UNIFIED_CHROMA)
    if mode == "vector":
        return store.query(q, k=k)
    bm25 = BM25Store(_BM25_PATH)
    if bm25.count() == 0:
        log.warning("retrieve.bm25_empty", hint="run --ingest --reset; fallback to vector")
        return store.query(q, k=k)
    return HybridRetriever(store, bm25).query(q, k=k)


def _retrieve_and_maybe_rerank(
    q: str,
    k: int,
    mode: str,
    *,
    do_rerank: bool,
) -> list[dict]:
    """先多召回，可选重排后再截断到 k。"""
    if not do_rerank:
        return _retrieve(q, k, mode)

    # 重排需要更多候选，否则精排空间太小，最少 12 条
    candidate_k = max(k * 3, 12)
    candidates = _retrieve(q, candidate_k, mode)
    return rerank(q, candidates, top_k=k)


def _print_chunks(chunks: list[dict]) -> None:
    print(Fore.BLUE, "\n--- retrieved chunks ---")
    for i, c in enumerate(chunks, 1):
        src = Path(c["source"]).name
        preview = c["text"].replace("\n", " ")[:120]
        print(f"[{i}] {src} (score={c['score']:.3f}) \n {preview}...")
    print("--- end chunks ---", Fore.RESET, "\n")


def retrieve_chunks(
    q: str,
    k: int = 4,
    *,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
) -> list[dict]:
    """仅检索，返回 top-k chunks（供 eval 测 recall@k；与生成共用同一检索路径）。"""
    configure_logging()
    store = VectorStore(chroma_path=_UNIFIED_CHROMA)
    if store.count() == 0:
        log.error("retrieve.empty_store", hint="run --ingest first")
        return []

    mode = retrieve if retrieve in {"hybrid", "vector"} else "hybrid"
    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank
    chunks = _retrieve_and_maybe_rerank(q, k, mode, do_rerank=do_rerank)
    log.info(
        "retrieve.done",
        mode=mode,
        rerank=do_rerank,
        k=k,
        top_score=chunks[0]["score"] if chunks else None,
    )
    return chunks


def query(
    q: str,
    k: int = 4,
    *,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
) -> str:
    """检索统一知识库并生成回答；若配置了 Langfuse，整条链路写入一条 trace。"""
    store = VectorStore(chroma_path=_UNIFIED_CHROMA)
    if store.count() == 0:
        log.error("query.empty_store", hint="run --ingest first")
        return "知识库为空。请先执行：python -m rag_assistant.pipeline --ingest --reset"

    mode = retrieve if retrieve in {"hybrid", "vector"} else "hybrid"
    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank

    def _run_retrieve() -> list[dict]:
        return retrieve_chunks(q, k=k, retrieve=mode, use_rerank=do_rerank)

    lf = get_langfuse()
    if lf is None:
        chunks = _run_retrieve()
        _print_chunks(chunks)
        return generate(q, chunks)

    try:
        with lf.start_as_current_observation(
            name="rag-query",
            as_type="chain",
            input={"query": q, "k": k, "retrieve": mode, "rerank": do_rerank},
        ) as root:
            with lf.start_as_current_observation(
                name="retrieve",
                as_type="retriever",
                input={"query": q, "k": k, "mode": mode, "rerank": do_rerank},
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
            _print_chunks(chunks)
            answer = generate(q, chunks)
            root.update(output={"answer": answer})
        return answer
    finally:
        flush_langfuse()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="内部知识助手（RAG）— 统一知识库，用户无需选库"
    )
    parser.add_argument("--ingest", action="store_true", help="构建/重建统一向量索引")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="配合 --ingest：清空统一向量库后重建",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="可选：仅入库某个语料包目录名（调试用）；默认入库全部",
    )
    parser.add_argument("--query", type=str, help="提出问题（自动查全部已入库知识）")
    parser.add_argument("--k", type=int, default=4, help="检索返回的 chunk 条数")
    parser.add_argument(
        "--retrieve",
        choices=("hybrid", "vector"),
        default="hybrid",
        help="检索模式：hybrid=向量+BM25（默认）；vector=仅向量（对照用）",
    )
    parser.add_argument(
        "--rerank",
        dest="use_rerank",
        action="store_true",
        default=None,
        help="启用重排（覆盖 .env 中 RERANK_ENABLED）",
    )
    parser.add_argument(
        "--no-rerank",
        dest="use_rerank",
        action="store_false",
        help="关闭重排（对照用）",
    )
    args = parser.parse_args()

    try:
        if args.ingest:
            ingest(reset=args.reset, only=args.only)
        elif args.query:
            print(Fore.CYAN, f"\nQ: {args.query}", Fore.RESET, "\n")
            print(
                Fore.CYAN,
                "A:",
                query(
                    args.query,
                    k=args.k,
                    retrieve=args.retrieve,
                    use_rerank=args.use_rerank,
                ),
                Fore.RESET,
            )
        else:
            parser.print_help()
            sys.exit(1)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
