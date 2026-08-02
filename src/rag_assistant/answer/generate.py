"""生成：把检索到的片段变成带引用的回答。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.config import get_settings
from ..core.llm import LLMClient
from ..core.logging import get_logger
from ..core.observability import get_langfuse
from .refusal import REFUSAL_MESSAGE, RefusalReason, is_refusal, pre_llm_refusal

log = get_logger(__name__)

_PREVIEW_LEN = 160
_CITATION_RE = re.compile(r"\[(\d+)\]")

_SYSTEM = """你是「星云科技」内部知识助手。只能根据提供的上下文片段回答员工关于制度、流程、产品内部说明的问题。

规则：
1. 严格依据上下文作答；若上下文没有答案，回复「{refusal}」不要猜测或编造制度条款。
2. 正文中引用事实时用 [1]、[2]… 标注依据的片段编号（可多处引用同一编号）。
3. 表述简洁，可直接引用制度中的数字、链接、审批角色。
4. 若不同片段互相矛盾，明确指出并建议咨询责任部门。
5. 不要在正文末尾单独罗列「参考来源」——来源列表由系统自动追加。
""".format(refusal=REFUSAL_MESSAGE)


@dataclass(frozen=True)
class Citation:
    index: int
    source: str
    source_path: str
    score: float
    preview: str
    cited: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _chunk_preview(text: str, limit: int = _PREVIEW_LEN) -> str:
    preview = text.replace("\n", " ").strip()
    if len(preview) > limit:
        return preview[:limit] + "…"
    return preview


def cited_indices(answer: str) -> set[int]:
    return {int(m) for m in _CITATION_RE.findall(answer)}


def build_citations(chunks: list[dict], answer: str) -> list[Citation]:
    """根据 Agent 终答中的 [1][2] 标记，标记哪些 chunk 被引用（ReAct 与 direct 共用）。"""
    used = cited_indices(answer)
    citations: list[Citation] = []
    for i, chunk in enumerate(chunks, 1):
        src_path = chunk.get("source", "?")
        citations.append(
            Citation(
                index=i,
                source=Path(src_path).name,
                source_path=src_path,
                score=float(chunk.get("score", 0.0)),
                preview=_chunk_preview(chunk.get("text", "")),
                cited=i in used,
            )
        )
    return citations


def format_sources_block(citations: list[Citation]) -> str:
    if not citations:
        return ""

    lines = ["", "---", "参考来源："]
    for c in citations:
        tag = "已引用" if c.cited else "检索命中"
        lines.append(f"[{c.index}] {c.source}  ({tag}, score={c.score:.3f})")
        lines.append(f"    {c.preview}")
    return "\n".join(lines)


def format_answer_with_sources(answer: str, chunks: list[dict]) -> str:
    block = format_sources_block(build_citations(chunks, answer))
    if not block:
        return answer
    return answer.rstrip() + block


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(f"[{i}] (source: {c['source']})\n{c['text']}")
    return "\n\n---\n\n".join(parts)


def generate(query: str, chunks: list[dict], *, tier: str = "strong") -> str:
    if not chunks:
        return REFUSAL_MESSAGE

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


def produce_answer(
    query: str,
    chunks: list[dict],
    *,
    use_rerank: bool,
    tier: str = "strong",
) -> tuple[str, bool, RefusalReason | None]:
    reason = pre_llm_refusal(chunks, use_rerank=use_rerank)
    if reason is not None:
        log.info(
            "refuse.pre_llm",
            reason=reason.value,
            top_score=chunks[0]["score"] if chunks else None,
        )
        return REFUSAL_MESSAGE, True, reason

    answer = generate(query, chunks, tier=tier)
    refused = is_refusal(answer)
    return answer, refused, RefusalReason.MODEL if refused else None
