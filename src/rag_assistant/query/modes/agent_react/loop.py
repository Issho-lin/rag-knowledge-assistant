"""ReAct 循环：LangChain Agent 图驱动「思考 → 调工具 → 读 Observation → 作答」。

本文件不手写 while 循环，由 ``create_agent`` 维护消息状态机；
工具侧只返回检索片段文本，最终答案从最后一条无 tool_calls 的 AIMessage 提取。
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ....kb.search import KbToolRunContext, ToolSearchResult, build_kb_tools
from ....core.logging import get_logger
from .llm import react_llm
from .prompts import REACT_SYSTEM

log = get_logger(__name__)


@dataclass(frozen=True)
class ReactAgentResult:
    """一次 ReAct 运行的原始产物（尚未封装为 QueryResult）。"""

    answer: str  # Agent 最终自然语言答复
    tool_results: tuple[ToolSearchResult, ...]  # 各次工具调用的结构化检索结果（不可变元组）
    tools_used: tuple[str, ...]  # 按调用顺序记录的工具名


def _message_content(message: BaseMessage) -> str:
    """从 AIMessage 取出纯文本（兼容 str 与多模态 content 块）。"""
    content = message.content  # LangChain 消息体：可能是 str 或 list[块]
    if isinstance(content, str):
        return content.strip()  # 最常见：整段字符串
    if isinstance(content, list):
        parts: list[str] = []  # 收集各文本块
        for block in content:  # 遍历多模态 content 数组
            if isinstance(block, str):
                parts.append(block)  # 纯字符串块
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))  # OpenAI 风格 text 块
        return "".join(parts).strip()  # 拼接后去空白
    return str(content).strip()  # 其它类型兜底转成字符串


def _extract_final_answer(messages: list[BaseMessage]) -> str:
    """取最后一条「纯文本、无 tool_calls」的 AIMessage 作为最终答案。"""
    for message in reversed(messages):  # 从后往前找，优先最近一条 AI 回复
        if not isinstance(message, AIMessage):
            continue  # 跳过 HumanMessage、ToolMessage 等
        if message.tool_calls:
            continue  # 带 tool_calls 的是「要继续调工具」轮，不是给用户看的终答
        text = _message_content(message)  # 解析出纯文本
        if text:
            return text  # 找到非空终答即返回
    return ""  # 全程没有终答（异常或 Agent 未输出）


def run_react_agent(
    question: str,  # 进入 Agent 的问句（通常已是 rewrite 后的 search_q）
    *,
    k: int = 4,  # 每次工具 retrieve 的 top-k
    retrieve: str = "hybrid",  # hybrid 或 vector
    use_rerank: bool | None = None,  # 工具内是否 rerank
    max_iterations: int = 6,  # 最多允许多少轮「调工具」循环
) -> ReactAgentResult:
    """ReAct 循环：Agent 自行决定调用哪些 KB 工具，并综合 Observation 作答。"""
    context = KbToolRunContext()  # 空记账本；工具执行时往 results 里 append
    tools = build_kb_tools(  # policies/tabular/pdf/relations 各一个 StructuredTool
        k=k,
        retrieve=retrieve,
        use_rerank=use_rerank,
        context=context,  # 同一 context 引用传入，闭包内共享，供工具执行时写入检索结果
    )
    graph = create_agent(react_llm(), tools, system_prompt=REACT_SYSTEM)  # 绑定 LLM+工具+系统提示
    state = graph.invoke(  # 同步执行 Agent 图直至终答或达 recursion_limit
        {"messages": [HumanMessage(content=question)]},  # 初始状态：仅一条用户消息
        config={"recursion_limit": max_iterations * 2 + 1},  # 图步数上限，防死循环
    )
    messages = state["messages"]  # 完整对话轨迹：Human / AI / Tool 交替
    answer = _extract_final_answer(messages)  # 从轨迹中抠出最终答复文本
    tools_used = tuple(r.tool_name for r in context.results)  # 从记账本提取工具名序列
    log.info(
        "agent.react_done",  # 结构化日志事件名
        tools=tools_used,
        tool_calls=len(context.results),  # 实际调用了几次工具
        question=question[:80],  # 问句截断，避免日志过长
    )
    # 返回 ReAct 循环的原始产物：最终答案 + 各次工具调用结果 + 工具名序列
    return ReactAgentResult(
        answer=answer,
        tool_results=tuple(context.results),  # 拷贝为不可变元组返回上层
        tools_used=tools_used,
    )
