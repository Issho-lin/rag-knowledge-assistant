"""生成：把检索到的片段变成带引用的回答。

要求：只依据上下文作答；无依据则拒答；回答末尾标注来源编号。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from .config import get_settings
from .llm import LLMClient
from .logging import get_logger
from .observability import get_langfuse

log = get_logger(__name__)

_SYSTEM = """你是「星云科技」内部知识助手。只能根据提供的上下文片段回答员工关于制度、流程、产品内部说明的问题。

规则：
1. 严格依据上下文作答；若上下文没有答案，回复「根据现有内部文档，我无法确认。」不要猜测或编造制度条款。
2. 回答末尾用 [1]、[2]… 标注依据的片段编号。
3. 表述简洁，可直接引用制度中的数字、链接、审批角色。
4. 若不同片段互相矛盾，明确指出并建议咨询责任部门。
"""


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(f"[{i}] (source: {c['source']})\n{c['text']}")
    return "\n\n---\n\n".join(parts)


def generate(query: str, chunks: list[dict], *, tier: str = "strong") -> str:
    """根据检索片段生成带引用的答案。"""
    if not chunks:
        return "根据现有内部文档，我无法确认。"

    context = _format_context(chunks)
    s = get_settings()
    model = s.chat_model_strong if tier == "strong" else s.chat_model_cheap
    user_content = f"上下文：\n{context}\n\n问题：{query}\n\n回答："
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=user_content),
    ]

    lf = get_langfuse()
    if lf is None:
        answer = LLMClient().invoke(messages, tier=tier)
        log.info("generate.done", query=query, n_chunks=len(chunks), tier=tier)
        return answer

    with lf.start_as_current_observation(
        name="generate",
        as_type="generation",
        model=model,
        input={
            "system": _SYSTEM,
            "user": user_content,
            "n_chunks": len(chunks),
            "tier": tier,
        },
        metadata={"tier": tier},
    ) as gen:
        answer = LLMClient().invoke(messages, tier=tier)
        gen.update(output=answer)
        log.info("generate.done", query=query, n_chunks=len(chunks), tier=tier)
        return answer
