"""拒答策略：统一文案、检测与检索置信度门槛。

产品侧与 eval 共用 is_refusal()，避免 prompt 与打分各写一套。
"""

from __future__ import annotations

from enum import Enum

from .config import get_settings

# 全项目唯一拒答句式（eval 用「无法确认」子串匹配）
REFUSAL_MESSAGE = "根据现有内部文档，我无法确认。"


class RefusalReason(str, Enum):
    NO_CHUNKS = "no_chunks"
    LOW_CONFIDENCE = "low_confidence"
    MODEL = "model"


def normalize_for_match(text: str) -> str:
    """比对前去掉半角/全角空格（与 eval scoring 一致）。"""
    return text.replace(" ", "").replace("\u3000", "")


def is_refusal(answer: str) -> bool:
    """答案是否为拒答（含「无法确认」即视为拒答）。"""
    return "无法确认" in normalize_for_match(answer)


def _is_rrf_score(score: float) -> bool:
    """混合检索 RRF 分数量纲很小（约 0.01～0.05），不宜做拒答阈值。"""
    return score < 0.1


def should_refuse_low_confidence(
    chunks: list[dict],
    *,
    use_rerank: bool,
    min_rerank_score: float | None = None,
    min_vector_score: float | None = None,
) -> bool:
    """检索 top-1 分数过低时拒答（不调用 LLM，避免硬编）。"""
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
    """生成前是否应直接拒答。

    rerank 路径下分数过滤已在 retrieve 阶段完成（滤空即 chunks=[]）；
    此处不再重复看 top-1，仅处理空列表。未 rerank 时仍用向量分门槛。
    """
    # 如果检索结果为空，则返回 NO_CHUNKS
    if not chunks:
        return RefusalReason.NO_CHUNKS
    # 如果启用重排，则不拒答
    if use_rerank:
        # 不拒答，返回 None
        return None
    # 如果没有启用重排，则判断是否需要拒答
    # 如果检索结果分数过低，则拒答
    if should_refuse_low_confidence(chunks, use_rerank=use_rerank):
        # 拒答，返回 LOW_CONFIDENCE
        return RefusalReason.LOW_CONFIDENCE
    return None
