"""端到端 RAG 流水线：入库 → 检索 → 生成。

产品语义（智能客服）：用户只提问，系统检索全部已入库知识，不选库。

    uv run python -m rag_assistant.pipeline --ingest --reset
    uv run python -m rag_assistant.pipeline --query "年假怎么算"
    uv run python -m rag_assistant.pipeline --chat

新增知识：把文件放进 data/corpus/<任意名>/{markdown,html,csv}/，再执行一次 --ingest --reset。

建库与问答分开：入库贵且慢；问答只嵌问题向量。
默认：向量+BM25 混合（RRF）+ 重排；可用 --retrieve / --no-rerank 做对照。

基础流程：
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
from dataclasses import dataclass
from pathlib import Path

from .config import get_settings
from .conversation import ChatTurn
from .generation import (
    Citation,
    build_citations,
    format_answer_with_sources,
    format_sources_block,
    produce_answer,
)
from .ingest.chunking import chunk_document
from .ingest.loaders import Document, load_corpus
from .kb import kb_profile_for_doc, resolve_kb_id
from .logging import configure_logging, get_logger
from .observability import flush_langfuse, get_langfuse
from .query_rewrite import rewrite_for_retrieval
from .refusal import RefusalReason
from .retrieval.bm25 import BM25Store
from .retrieval.engine import retrieve_with_options
from .retrieval.metadata import build_chunk_metadata
from .retrieval.options import RetrievalOptions
from .retrieval.vector import VectorStore

from colorama import Fore

log = get_logger(__name__)

# 统一向量库（客服只查这一个库）；语料父目录见配置 CORPUS_DIR
_UNIFIED_CHROMA = Path("data/chroma/unified")

def _merge_retrieval_options(
    options: RetrievalOptions | None,
    kb_id: str | None,
) -> RetrievalOptions:
    """未指定 kb 时用全局默认；指定 kb 时用该库 Profile + kb 元数据过滤。"""
    # 如果未指定知识库，则返回全局默认检索选项
    if kb_id is None:
        return options or RetrievalOptions.from_settings()
    from .kb import get_kb
    # 获取知识库检索选项
    kb_opts = get_kb(kb_id).profile.retrieval
    # 构建元数据过滤条件
    meta = {"kb": kb_id, **kb_opts.metadata_filter}
    # 如果全局检索选项有元数据过滤条件，则合并
    if options and options.metadata_filter:
        meta.update(options.metadata_filter)
    # 返回合并后的检索选项
    return RetrievalOptions(
        decompose=kb_opts.decompose,
        expand_parent=kb_opts.expand_parent,
        metadata_filter=meta,
    )


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
    # 发现所有语料包
    roots = discover_corpus_roots()
    # 如果只加载指定语料包，则只加载那一包
    if only:
        roots = [r for r in roots if r.name == only]
        if not roots:
            raise FileNotFoundError(
                f"未找到语料包 {only!r}。当前可用: {[r.name for r in discover_corpus_roots()]}"
            )

    # 加载全部语料
    docs: list[Document] = []
    # 遍历所有语料包
    for root in roots:
        # 加载语料包
        part = load_corpus(root)
        # 设置语料包名称
        for d in part:
            d.metadata.setdefault("corpus", root.name)
        docs.extend(part)
        log.info("ingest.load_bundle", corpus=root.name, docs=len(part))
    return docs


def ingest(*, reset: bool = False, only: str | None = None) -> int:
    """将知识库全部（或指定包）切块入库：向量库 + BM25。"""
    # 配置日志
    configure_logging()
    # 加载全部语料
    docs = load_all_documents(only=only)
    # 如果语料为空，则提示执行入库命令
    if not docs:
        log.error("ingest.empty", parent=str(get_settings().corpus_dir))
        print("未找到任何语料。请在 data/corpus/<名称>/{markdown,html,csv}/ 下放置文件。")
        return 0

    # 初始化向量库
    chroma_path = _UNIFIED_CHROMA
    # 如果需要重置，则清空向量库
    if reset and chroma_path.exists():
        shutil.rmtree(chroma_path)
        log.info("ingest.reset_store", path=str(chroma_path))

    # 初始化切块结果
    all_ids: list[str] = []
    all_chunks: list[str] = []
    all_sources: list[str] = []
    all_metadatas: list[dict[str, str | int]] = []
    # 遍历所有语料
    for d in docs:
        # 语料包名称
        corpus_name = str(d.metadata.get("corpus", "?"))
        # 语料类型
        kind = str(d.metadata.get("kind", ""))
        # 知识库 ID
        kb_id = resolve_kb_id(d)
        # 获取知识库配置
        profile = kb_profile_for_doc(d)
        # 切块-根据知识库配置切块，返回ChunkInfo列表
        chunk_infos = chunk_document(d, profile.max_chars, profile.chunk_strategy)
        # 遍历ChunkInfo列表
        for i, info in enumerate(chunk_infos):
            # 生成chunk id
            all_ids.append(_chunk_id(d.source, info.text, i))
            # 添加chunk文本
            all_chunks.append(info.text)
            # 添加chunk来源
            all_sources.append(d.source)
            # 添加chunk元数据
            all_metadatas.append(
                build_chunk_metadata(
                    source=d.source,
                    kind=kind,
                    corpus=corpus_name,
                    kb=kb_id,
                    parent_text=info.parent_text,
                    chunk_index=info.chunk_index,
                )
            )

    if not all_chunks:
        print("切块结果为空，未写入索引。")
        return 0
    # 初始化向量库
    store = VectorStore(chroma_path=chroma_path)
    # 添加chunk到向量库
    total = store.add(all_chunks, all_sources, ids=all_ids, metadatas=all_metadatas)
    # 初始化BM25索引
    bm25 = BM25Store(_BM25_PATH)
    # 重建BM25索引
    bm25.rebuild(all_ids, all_chunks, all_sources, metadatas=all_metadatas)

    # 获取语料包名称列表
    bundles = sorted({d.metadata.get("corpus", "?") for d in docs})
    # 记录日志
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
        chroma_path=_UNIFIED_CHROMA,
        bm25_path=_BM25_PATH,
    )


@dataclass
class QueryResult:
    """一次问答的完整结果：正文、检索片段、结构化引用。"""

    answer: str
    chunks: list[dict]
    citations: list[Citation]
    refused: bool = False
    refusal_reason: RefusalReason | None = None
    rewritten_query: str | None = None

    def display_text(self) -> str:
        """供 CLI 打印：正文 + 参考来源块。"""
        return format_answer_with_sources(self.answer, self.chunks)

    def sources_text(self) -> str:
        return format_sources_block(self.citations)

    def refusal_note(self) -> str | None:
        """拒答原因的人类可读说明（CLI 用）。"""
        if not self.refused or self.refusal_reason is None:
            return None
        labels = {
            RefusalReason.NO_CHUNKS: "未检索到相关片段",
            RefusalReason.LOW_CONFIDENCE: "检索置信度过低",
            RefusalReason.MODEL: "模型判断文档无依据",
        }
        return labels.get(self.refusal_reason, self.refusal_reason.value)


def retrieve_chunks(
    q: str,
    k: int = 4,
    *,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
    options: RetrievalOptions | None = None,
    kb_id: str | None = None,
) -> list[dict]:
    """仅检索，返回 top-k chunks（供 eval 测 recall@k；与生成共用同一检索路径）。"""

    # 配置日志
    configure_logging()
    # 初始化向量库
    store = VectorStore(chroma_path=_UNIFIED_CHROMA)
    # 如果向量库为空，则提示执行入库命令
    if store.count() == 0:
        log.error("retrieve.empty_store", hint="run --ingest first")
        return []

    mode = _normalize_retrieve_mode(retrieve)
    # 判断是否启用重排
    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank
    # 合并检索选项
    opts = _merge_retrieval_options(options, kb_id)
    # 调用检索函数，传入查询、返回条数、检索模式、是否启用重排、检索选项
    chunks = _retrieve_and_maybe_rerank(q, k, mode, do_rerank=do_rerank, options=opts)
    # 记录检索完成
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
    store = VectorStore(chroma_path=_UNIFIED_CHROMA)
    # 如果向量库为空，则提醒执行入库命令
    if store.count() == 0:
        log.error("query.empty_store", hint="run --ingest first")
        msg = "知识库为空。请先执行：python -m rag_assistant.pipeline --ingest --reset"
        return QueryResult(answer=msg, chunks=[], citations=[], refused=True)

    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank
    # 改写查询
    search_q = rewrite_for_retrieval(q, history)

    def _run_retrieve() -> list[dict]:
        # 调用检索函数，传入改写后的查询、返回条数、检索模式、是否启用重排、知识库 ID
        # 检索函数返回检索结果，即 top-k chunks
        return retrieve_chunks(
            search_q, k=k, retrieve=retrieve, use_rerank=do_rerank, kb_id=kb_id
        )

    def _finish(chunks: list[dict]) -> QueryResult:
        # 调用生成答案函数，传入改写后的查询、检索结果、是否启用重排
        # 生成答案函数返回答案、拒答原因、拒答原因的人类可读说明
        answer, refused, reason = produce_answer(search_q, chunks, use_rerank=do_rerank)
        # 构造 QueryResult 对象，返回答案、检索结果、引用、拒答状态、拒答原因、改写后的查询
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

    retrieve_mode = _normalize_retrieve_mode(retrieve)
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


def _print_query_result(question: str, result: QueryResult) -> None:
    print(f"{Fore.CYAN}\nQ: {question}\n{Fore.RESET}", end="")
    if result.rewritten_query:
        print(f"{Fore.CYAN}检索问句: {result.rewritten_query}\n{Fore.RESET}", end="")
    print(f"{Fore.MAGENTA}\nA: {result.answer}\n{Fore.RESET}", end="")
    note = result.refusal_note()
    if note:
        print(f"{Fore.YELLOW}（拒答：{note}）{Fore.RESET}")
    if result.citations:
        print(f"{Fore.BLUE}{result.sources_text()}{Fore.RESET}")


def chat(
    k: int = 4,
    *,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
) -> None:
    """交互式多轮问答；输入 exit / quit / q 退出。"""
    # 配置日志
    configure_logging()
    # 初始化历史记录
    history: list[ChatTurn] = []
    print("星云科技内部知识助手（多轮）。输入 exit / quit / q 退出。\n")

    # 多轮对话
    while True:
        # 尝试读取用户输入
        try:
            question = input(f"{Fore.GREEN}You: {Fore.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            break

        # 调用 query 函数，传入用户输入、返回条数、历史记录、检索模式、是否启用重排
        # query 函数返回查询结果
        result = query(
            question,
            k=k,
            history=history,
            retrieve=retrieve,
            use_rerank=use_rerank,
        )
        _print_query_result(question, result)
        # 将用户输入和查询结果添加到历史记录中
        history.append(ChatTurn(role="user", content=question))
        history.append(ChatTurn(role="assistant", content=result.answer))


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
    parser.add_argument(
        "--kb",
        type=str,
        default=None,
        choices=("policies", "tabular", "pdf"),
        help="可选：仅检索指定知识库（调试用；默认查全部）",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="交互式多轮问答（结合历史做 query 改写后再检索）",
    )
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
        elif args.chat:
            chat(k=args.k, retrieve=args.retrieve, use_rerank=args.use_rerank)
        elif args.query:
            result = query(
                args.query,
                k=args.k,
                retrieve=args.retrieve,
                use_rerank=args.use_rerank,
                kb_id=args.kb,
            )
            _print_query_result(args.query, result)
        else:
            parser.print_help()
            sys.exit(1)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
