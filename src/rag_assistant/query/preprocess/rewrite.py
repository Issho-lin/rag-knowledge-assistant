"""多轮 query 改写：ReAct 编排层在 ``run_react_agent`` 之前调用。

无历史时跳过 LLM；有历史时把指代问句补全为可独立检索的 ``search_q``。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ...conversation import ChatTurn, format_history, trim_history
from ...core.llm import LLMClient
from ...core.logging import get_logger
from ...core.observability import get_langfuse

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
    """无历史或空问题时原样返回；否则用 cheap LLM 生成独立检索问句。"""
    q = question.strip()
    if not q:
        return question
    trimmed = trim_history(history)
    if not trimmed:
        return q  # 单轮 ReAct：search_q == 用户原问

    messages = build_rewrite_messages(q, trimmed)
    lf = get_langfuse()

    if lf is None:
        rewritten = LLMClient().invoke(messages, tier=tier)
    else:
        with lf.start_as_current_observation(
            name="query-rewrite",
            as_type="generation",
            input={"question": q, "history_turns": len(trimmed)},
        ) as obs:
            rewritten = LLMClient().invoke(messages, tier=tier)
            obs.update(output=rewritten)

    out = _normalize_rewrite(rewritten)
    if out != q:
        log.info("rewrite.done", original=q, rewritten=out)
    else:
        log.info("rewrite.unchanged", query=q)
    return out
