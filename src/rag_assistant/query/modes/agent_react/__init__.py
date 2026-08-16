"""--react 主路径编排：改写 → ReAct 循环 → 组装 QueryResult。

与 ``--query`` / ``--agent`` 不同，最终答案由 Agent 根据 Observation 写出，
不经过 ``produce_answer``；本模块负责入口校验、可观测性与结果封装。
"""

from __future__ import annotations

from ....core.config import get_settings
from ....conversation import ChatTurn
from ....answer import build_citations
from ....answer.refusal import RefusalReason, is_refusal
from ....core.observability import flush_langfuse, get_langfuse
from ...helpers import ensure_store_ready
from ...preprocess.rewrite import rewrite_for_retrieval
from ...result import QueryResult
from .loop import ReactAgentResult, run_react_agent

__all__ = ["ReactAgentResult", "query_agent_react", "run_react_agent"]


def _tool_results_to_query_result(
    *,
    question: str,  # 用户原始问句（CLI 展示用，可能与 search_q 不同）
    search_q: str,  # 实际进入 ReAct 的检索问句（多轮改写后）
    answer: str,  # Agent 最终自然语言答复
    tool_results: list,  # 各次工具调用的 ToolSearchResult 列表
    tools_used: tuple[str, ...],  # 按调用顺序的工具名，如 search_policies
) -> QueryResult:
    """把 ReAct 循环产物转成 CLI / eval 统一的 ``QueryResult``。"""
    chunks: list[dict] = []  # 合并所有工具返回的原始检索片段
    for result in tool_results:  # 遍历每一次 search_* 调用
        chunks.extend(result.chunks)  # 把该次工具的 chunks 追加进总列表

    last = tool_results[-1] if tool_results else None  # 最后一次工具调用（用于 routed_kb_id）
    final_answer = answer.strip() or "未能生成回答。"  # 去掉首尾空白；空则给默认文案
    refused = False  # 是否判定为拒答
    refusal_reason: RefusalReason | None = None  # 拒答原因：无片段 / 模型判断等
    if not chunks and is_refusal(final_answer):  # 完全没检索到且答案像拒答
        refused = True
        refusal_reason = RefusalReason.NO_CHUNKS  # 归因：检索侧无依据
    elif is_refusal(final_answer):  # 有 chunks 但 Agent 仍输出「无法确认」
        refused = True
        refusal_reason = RefusalReason.MODEL  # 归因：模型读完 Observation 后拒答
    routed_tool = ",".join(tools_used) if tools_used else None  # 多个工具用逗号拼接展示
    routed_kb_id = last.kb_id if last else None  # 最后一次工具对应的知识库 id

    return QueryResult(
        answer=final_answer,  # 给用户看的正文
        chunks=chunks,  # 结构化检索结果，供侧栏与调试
        citations=build_citations(chunks, final_answer),  # 解析 [1][2] 生成参考来源块
        refused=refused,
        refusal_reason=refusal_reason,
        rewritten_query=search_q if search_q != question.strip() else None,  # 仅改写过时展示
        routed_tool=routed_tool,
        routed_kb_id=routed_kb_id,
    )


def query_agent_react(
    q: str,  # 用户当前轮输入的问题
    k: int = 4,  # 每次工具检索返回的 chunk 条数
    *,
    history: list[ChatTurn] | None = None,  # 多轮历史；None 或空表示单轮
    retrieve: str = "hybrid",  # 检索模式：hybrid 或 vector
    use_rerank: bool | None = None,  # 是否重排；None 则用配置默认
) -> QueryResult:
    """ReAct Agent：LLM 循环调用 KB 工具，综合 Observation 后作答。"""
    if (empty := ensure_store_ready()) is not None:  # 未 ingest 则直接返回空库提示
        return empty
    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank  # 解析 rerank 开关
    search_q = rewrite_for_retrieval(q, history)  # 有历史则 cheap 模型改写；无历史则原样

    def _run() -> QueryResult:
        """实际执行 ReAct 并封装结果；供无 Langfuse 与有 Langfuse 两条路径复用。"""
        react_result = run_react_agent(  # 进入 LangChain Agent 图
            search_q,  # 传入改写后的问句（Agent 只见这一条 HumanMessage）
            k=k,
            retrieve=retrieve,
            use_rerank=do_rerank,
        )
        return _tool_results_to_query_result(  # ReactAgentResult → QueryResult
            question=q,  # 保留用户原文用于展示与 rewritten_query 对比
            search_q=search_q,
            answer=react_result.answer,
            tool_results=list(react_result.tool_results),  # tuple 转 list 无功能差异
            tools_used=react_result.tools_used,
        )

    lf = get_langfuse()  # 若未配置 Langfuse 环境变量则为 None
    if lf is None:
        return _run()  # 无可观测时直接跑，少一层 span 包装

    try:
        with lf.start_as_current_observation(  # 外层：整次用户提问的 chain
            name="rag-react-query",
            as_type="chain",
            input={"query": q, "rewritten_query": search_q},  # 记录原问与改写问
        ) as root:
            with lf.start_as_current_observation(  # 内层：Agent 执行段
                name="agent-react",
                as_type="agent",
                input={"query": search_q},
            ):
                result = _run()  # 在 agent span 内执行 ReAct
            root.update(  # 把关键输出写回外层 span，便于平台检索
                output={
                    "answer": result.answer,
                    "routed_tool": result.routed_tool,
                    "routed_kb_id": result.routed_kb_id,
                    "refused": result.refused,
                }
            )
        return result
    finally:
        flush_langfuse()  # 确保 trace 数据发送完成（短请求进程否则可能丢）
