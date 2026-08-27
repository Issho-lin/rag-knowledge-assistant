"""CRAG 控制流单测（不连真实 LLM）。"""

from __future__ import annotations

from unittest.mock import patch

from rag_assistant.retrieval.crag import (
    _parse_grade,
    maybe_apply_crag,
    rewrite_query_for_crag,
)


def test_parse_grade_json_and_fence():
    assert _parse_grade('{"grade":"correct","reason":"ok"}') == "correct"
    assert _parse_grade('废话\n```json\n{"grade":"incorrect","reason":"x"}\n```') == "incorrect"
    assert _parse_grade("grade is ambiguous here") == "ambiguous"


def test_maybe_apply_crag_disabled_passthrough():
    chunks = [{"text": "a", "score": 0.9}]
    out = maybe_apply_crag(
        "q",
        chunks,
        retrieve_again=lambda _q: [{"text": "b"}],
        enabled=False,
    )
    assert out == chunks


@patch("rag_assistant.retrieval.crag.grade_retrieval", return_value="correct")
def test_maybe_apply_crag_correct_skips_retry(mock_grade):
    chunks = [{"text": "hit"}]
    called = {"n": 0}

    def again(_q: str):
        called["n"] += 1
        return [{"text": "retry"}]

    out = maybe_apply_crag("年假几天", chunks, retrieve_again=again, enabled=True)
    assert out == chunks
    assert called["n"] == 0
    mock_grade.assert_called_once()


@patch("rag_assistant.retrieval.crag.rewrite_query_for_crag", return_value="年假 折现 天数")
@patch("rag_assistant.retrieval.crag.grade_retrieval", return_value="incorrect")
def test_maybe_apply_crag_incorrect_retries(mock_grade, mock_rewrite):
    first = [{"text": "无关"}]
    second = [{"text": "年假 10 天"}]

    out = maybe_apply_crag(
        "年假有多少天",
        first,
        retrieve_again=lambda q: second if "年假" in q else [],
        enabled=True,
    )
    assert out == second
    mock_grade.assert_called_once()
    mock_rewrite.assert_called_once()


@patch("rag_assistant.retrieval.crag.LLMClient")
def test_rewrite_falls_back_on_llm_error(mock_llm_cls):
    mock_llm_cls.return_value.invoke.side_effect = RuntimeError("quota")
    assert rewrite_query_for_crag("原问", [{"text": "x"}]) == "原问"
