"""多轮 query 改写单测（不调用真实 LLM）。"""

from rag_assistant.conversation import ChatTurn, format_history, trim_history
from rag_assistant.query.preprocess.rewrite import build_rewrite_messages, rewrite_for_retrieval


def test_trim_history_keeps_tail():
    history = [
        ChatTurn("user", "u1"),
        ChatTurn("assistant", "a1"),
        ChatTurn("user", "u2"),
        ChatTurn("assistant", "a2"),
    ]
    trimmed = trim_history(history, max_messages=2)
    assert len(trimmed) == 2
    assert trimmed[0].content == "u2"
    assert trimmed[1].content == "a2"


def test_format_history_labels():
    history = [
        ChatTurn("user", "年假有多少天？"),
        ChatTurn("assistant", "满 1 年 5 天。"),
    ]
    text = format_history(history)
    assert "用户：年假有多少天？" in text
    assert "助手：满 1 年 5 天。" in text


def test_build_rewrite_messages_includes_history_and_question():
    history = [ChatTurn("user", "年假有多少天？"), ChatTurn("assistant", "5 天起。")]
    messages = build_rewrite_messages("那病假呢？", history)
    user = messages[1].content
    assert "年假有多少天？" in user
    assert "那病假呢？" in user


def test_rewrite_passthrough_without_history(monkeypatch):
    def _fail(*_args, **_kwargs):
        raise AssertionError("不应在无历史时调用 LLM")

    monkeypatch.setattr(
        "rag_assistant.query.preprocess.rewrite.LLMClient",
        lambda: type("X", (), {"invoke": _fail})(),
    )
    assert rewrite_for_retrieval("年假有多少天？") == "年假有多少天？"


def test_rewrite_passthrough_empty_question():
    assert rewrite_for_retrieval("   ") == "   "
