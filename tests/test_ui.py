"""Gradio UI 格式化逻辑单测（不启动 Web）。"""

from rag_assistant.generation import Citation
from rag_assistant.pipeline import QueryResult
from rag_assistant.refusal import RefusalReason
from rag_assistant.ui import format_result_detail


def test_format_detail_shows_rewritten_query():
    result = QueryResult(
        answer="病假需二级甲等证明。",
        chunks=[],
        citations=[],
        rewritten_query="病假超过两天要什么证明？",
    )
    text = format_result_detail(result)
    assert "检索问句" in text
    assert "病假超过两天要什么证明？" in text


def test_format_detail_shows_refusal_and_chunks():
    result = QueryResult(
        answer="根据现有内部文档，我无法确认。",
        chunks=[
            {
                "source": "data/corpus/internal/markdown/02-请假与考勤制度.md",
                "text": "年假 5 天起",
                "score": 0.06,
            }
        ],
        citations=[],
        refused=True,
        refusal_reason=RefusalReason.LOW_CONFIDENCE,
        rewritten_query=None,
    )
    text = format_result_detail(result)
    assert "拒答" in text
    assert "02-请假与考勤制度.md" in text
    assert "score=0.060" in text
