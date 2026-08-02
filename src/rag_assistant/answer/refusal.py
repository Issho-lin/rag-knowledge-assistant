"""拒答策略：ReAct 工具层 ``pre_llm_refusal`` 与终答 ``is_refusal`` 检测。"""

from __future__ import annotations

from enum import Enum

from ..core.config import get_settings

REFUSAL_MESSAGE = "根据现有内部文档，我无法确认。"


class RefusalReason(str, Enum):
    NO_CHUNKS = "no_chunks"
    LOW_CONFIDENCE = "low_confidence"
    MODEL = "model"


def normalize_for_match(text: str) -> str:
    return text.replace(" ", "").replace("\u3000", "")


def is_refusal(answer: str) -> bool:
    """检测 Agent / 模型终答是否含标准拒答话术（ReAct 封装 QueryResult 时用）。"""
    return "无法确认" in normalize_for_match(answer)


def _is_rrf_score(score: float) -> bool:
    return score < 0.1


def should_refuse_low_confidence(
    chunks: list[dict],
    *,
    use_rerank: bool,
    min_rerank_score: float | None = None,
    min_vector_score: float | None = None,
) -> bool:
    if not chunks:
        return False

    s = get_settings()
    top = float(chunks[0].get("score", 0.0))
    min_rerank = min_rerank_score if min_rerank_score is not None else s.refuse_min_rerank_score
    min_vector = min_vector_score if min_vector_score is not None else s.refuse_min_vector_score

    if use_rerank:
        return top < min_rerank
    if _is_rrf_score(top):
        return False
    return top < min_vector


def pre_llm_refusal(
    chunks: list[dict],
    *,
    use_rerank: bool,
) -> RefusalReason | None:
    """工具层检索后拒答判断：影响 Observation 文案，不直接终止 ReAct 循环。"""
    if not chunks:
        return RefusalReason.NO_CHUNKS
    # 启用 rerank 时以 cross-encoder 分数为准，不在此做低分拒答
    if use_rerank:
        return None
    if should_refuse_low_confidence(chunks, use_rerank=use_rerank):
        return RefusalReason.LOW_CONFIDENCE
    return None
