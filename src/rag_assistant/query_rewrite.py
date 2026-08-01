"""多轮 query 改写：结合历史把指代问句补全为可独立检索的完整问题。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from .conversation import ChatTurn, format_history, trim_history
from .llm import LLMClient
from .logging import get_logger
from .observability import get_langfuse

log = get_logger(__name__)

_REWRITE_SYSTEM = """你是「星云科技」内部知识助手的查询改写模块。

任务：根据对话历史，把用户的「最新问题」改写成一句可独立用于文档检索的完整中文问句。

规则：
1. 若最新问题已完整、无指代、可独立检索，原样输出，不要扩写。
2. 若含指代或省略（如「那病假呢」「还有呢」「他分机多少」），结合历史补全实体、主题与意图。
3. 只输出一句问句，不要解释、不要编号、不要引号包裹。
4. 保持公司内部问答语气；不要编造历史里没有出现过的具体人名、数字或制度条款。"""


def build_rewrite_messages(question: str, history: list[ChatTurn]) -> list:
    """构造改写用的 messages（便于单测与 Langfuse 记录）。"""
    hist_text = format_history(history)
    user_content = (
        f"对话历史：\n{hist_text}\n\n"
        f"最新问题：{question.strip()}\n\n"
        "改写后的检索问句："
    )
    return [
        SystemMessage(content=_REWRITE_SYSTEM),
        HumanMessage(content=user_content),
    ]


def _normalize_rewrite(text: str) -> str:
    """去掉模型可能加上的引号或多余空白。"""
    q = text.strip()
    for pair in (('"', '"'), ("「", "」"), ("“", "”"), ("'", "'")):
        if len(q) >= 2 and q.startswith(pair[0]) and q.endswith(pair[1]):
            q = q[1:-1].strip()
            break
    return q or text.strip()


def rewrite_for_retrieval(
    question: str,
    history: list[ChatTurn] | None = None,
    *,
    tier: str = "cheap",
) -> str:
    """无历史或空问题时原样返回；否则用 LLM 生成独立检索问句。"""
    q = question.strip()
    if not q:
        return question
    # 修剪历史记录，只保留最近若干条
    trimmed = trim_history(history)
    # 如果修剪后历史记录为空，则直接返回原始问题
    if not trimmed:
        return q

    # 构造指引模型进行改写的 messages
    messages = build_rewrite_messages(q, trimmed)
    # 获取 Langfuse 实例
    lf = get_langfuse()

    # 如果 Langfuse 实例为空，则直接调用 LLM 进行改写
    if lf is None:
        rewritten = LLMClient().invoke(messages, tier=tier)
    else:
        # 如果 Langfuse 实例不为空，则启动一个 Langfuse 观察，记录改写过程
        with lf.start_as_current_observation(
            name="query-rewrite",
            as_type="generation",
            input={"question": q, "history_turns": len(trimmed)},
        ) as obs:
            # 调用 LLM 进行改写
            rewritten = LLMClient().invoke(messages, tier=tier)
            obs.update(output=rewritten)

    # 对改写结果进行规范化处理
    out = _normalize_rewrite(rewritten)
    # 如果规范化后的结果与原始问题不同，则记录改写过程
    if out != q:
        log.info("rewrite.done", original=q, rewritten=out)
    # 如果规范化后的结果与原始问题相同，则记录改写过程
    else:
        log.info("rewrite.unchanged", query=q)
    # 返回规范化后的结果
    return out
