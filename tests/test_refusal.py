"""拒答策略单测。"""

from rag_assistant.answer.refusal import (
    REFUSAL_MESSAGE,
    RefusalReason,
    is_refusal,
    pre_llm_refusal,
    should_refuse_low_confidence,
)


def test_is_refusal_detects_message():
    assert is_refusal(REFUSAL_MESSAGE) is True
    assert is_refusal("年假 5 天") is False
    assert is_refusal("根据现有内部文档，我 无法 确认。") is True


def test_should_refuse_low_rerank_score():
    chunks = [{"source": "a.md", "text": "x", "score": 0.08}]
    assert should_refuse_low_confidence(chunks, use_rerank=True) is True
    assert should_refuse_low_confidence(chunks, use_rerank=True, min_rerank_score=0.05) is False


def test_skip_rrf_score_gate_without_rerank():
    chunks = [{"source": "a.md", "text": "x", "score": 0.032}]
    assert should_refuse_low_confidence(chunks, use_rerank=False) is False


def test_pre_llm_refusal_empty_chunks():
    assert pre_llm_refusal([], use_rerank=True) == RefusalReason.NO_CHUNKS


def test_pre_llm_refusal_low_confidence_vector_only():
    """未 rerank 时仍按向量余弦分门槛拒答；rerank 路径在 retrieve 阶段已滤分。"""
    chunks = [{"source": "a.md", "text": "x", "score": 0.30}]
    assert pre_llm_refusal(chunks, use_rerank=False) == RefusalReason.LOW_CONFIDENCE


def test_pre_llm_refusal_rerank_skips_top1_gate():
    """rerank 后低分应在 retrieve 滤掉；若仍有 chunk 则直接生成。"""
    chunks = [{"source": "a.md", "text": "x", "score": 0.20}]
    assert pre_llm_refusal(chunks, use_rerank=True) is None
