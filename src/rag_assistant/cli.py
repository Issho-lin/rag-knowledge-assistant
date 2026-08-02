"""命令行入口：argparse、交互式 chat、结果打印。

ReAct 主路径：``--react --query`` 或 ``--chat --react`` → ``query_agent_react``。
"""

from __future__ import annotations

import argparse
import sys

from colorama import Fore

from .conversation import ChatTurn
from .core.logging import configure_logging
from .ingest.run import ingest
from .query.modes import query, query_agent, query_agent_react
from .query.result import QueryResult


def print_query_result(question: str, result: QueryResult) -> None:
    """打印单次问答结果；ReAct 会额外展示改写问句与路由工具。"""
    print(f"{Fore.CYAN}\nQ: {question}\n{Fore.RESET}", end="")
    if result.rewritten_query:
        print(f"{Fore.CYAN}检索问句: {result.rewritten_query}\n{Fore.RESET}", end="")
    if result.routed_tool:
        # routed_tool 可能为 "search_policies,search_tabular"（多工具复合题）
        print(
            f"{Fore.CYAN}路由工具: {result.routed_tool}"
            f" (kb={result.routed_kb_id})\n{Fore.RESET}",
            end="",
        )
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
    use_agent: bool = False,
    use_react: bool = False,
) -> None:
    """交互式多轮问答；输入 exit / quit / q 退出。"""
    configure_logging()
    history: list[ChatTurn] = []
    if use_react:
        mode = "ReAct Agent"
        ask = query_agent_react  # 主路径：多工具 + Agent 写终答
    elif use_agent:
        mode = "Agent 路由"
        ask = query_agent
    else:
        mode = "全库"
        ask = query
    print(f"星云科技内部知识助手（多轮 · {mode}）。输入 exit / quit / q 退出。\n")

    while True:
        try:
            question = input(f"{Fore.GREEN}You: {Fore.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            break

        result = ask(
            question,
            k=k,
            history=history,
            retrieve=retrieve,
            use_rerank=use_rerank,
        )
        print_query_result(question, result)
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
    parser.add_argument(
        "--agent",
        action="store_true",
        help="由 Agent 自动选择 KB 工具（function calling 路由，单库 RAG）",
    )
    parser.add_argument(
        "--react",
        action="store_true",
        help="ReAct Agent 循环调用 KB 工具（可多工具、Agent 综合 Observation）",
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

    if args.agent and args.react:
        parser.error("--agent 与 --react 不能同时使用")

    try:
        if args.ingest:
            ingest(reset=args.reset, only=args.only)
        elif args.chat:
            chat(
                k=args.k,
                retrieve=args.retrieve,
                use_rerank=args.use_rerank,
                use_agent=args.agent,
                use_react=args.react,
            )
        elif args.query:
            # --react 与 --agent 由 Agent 选库，忽略 --kb
            if args.react:
                ask = query_agent_react
            elif args.agent:
                ask = query_agent
            else:
                ask = query
            result = ask(
                args.query,
                k=args.k,
                retrieve=args.retrieve,
                use_rerank=args.use_rerank,
                **({} if args.agent or args.react else {"kb_id": args.kb}),
            )
            print_query_result(args.query, result)
        else:
            parser.print_help()
            sys.exit(1)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
