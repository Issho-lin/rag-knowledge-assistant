"""Agent 路由与 KB 工具单测。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from rag_assistant.kb.search import build_kb_tools, format_chunks_observation
from rag_assistant.kb import get_kb_by_tool_name
from rag_assistant.query.modes.agent_react import run_react_agent
from rag_assistant.query.modes.agent_route import resolve_tool_to_kb_id, select_tool_names


def test_get_kb_by_tool_name():
    assert get_kb_by_tool_name("search_policies").id == "policies"
    assert get_kb_by_tool_name("search_tabular").id == "tabular"
    assert get_kb_by_tool_name("search_pdf_handbook").id == "pdf"


def test_resolve_tool_to_kb_id():
    assert resolve_tool_to_kb_id("search_tabular") == "tabular"


def test_build_kb_tools_names():
    names = {t.name for t in build_kb_tools()}
    assert names == {"search_policies", "search_tabular", "search_pdf_handbook"}


def test_format_chunks_observation_empty():
    text = format_chunks_observation([], kb_id="tabular")
    assert "未检索到相关片段" in text


def test_format_chunks_observation_with_chunks():
    text = format_chunks_observation(
        [{"source": "a.csv", "score": 0.9, "text": "工号=XY003"}],
        kb_id="tabular",
    )
    assert "检索到 1 条片段" in text
    assert "XY003" in text


@patch("rag_assistant.query.modes.agent_route.select.router_llm")
def test_select_tool_names(mock_llm_factory):
    mock_llm = MagicMock()
    mock_llm_factory.return_value = mock_llm
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound
    mock_bound.invoke.return_value = MagicMock(
        tool_calls=[{"name": "search_tabular", "args": {"query": "XY003"}, "id": "1"}]
    )
    names = select_tool_names("工号 XY003 是谁？")
    assert names == ["search_tabular"]


@patch("rag_assistant.query.modes.agent_route.select.router_llm")
def test_select_tool_names_empty_fallback(mock_llm_factory):
    mock_llm = MagicMock()
    mock_llm_factory.return_value = mock_llm
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound
    mock_bound.invoke.return_value = MagicMock(tool_calls=[])
    assert select_tool_names("随便问问") == []


@patch("rag_assistant.query.modes.agent_react.loop.create_agent")
def test_run_react_agent_invokes_graph(mock_create_agent):
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [AIMessage(content="张三在研发部，工号 XY003。")]
    }
    mock_create_agent.return_value = mock_graph

    with patch("rag_assistant.query.modes.agent_react.loop.build_kb_tools") as mock_build_tools:
        mock_build_tools.return_value = []
        result = run_react_agent("工号 XY003 是谁？", k=4)

    mock_graph.invoke.assert_called_once()
    assert result.answer == "张三在研发部，工号 XY003。"
    mock_build_tools.assert_called_once()
    assert mock_build_tools.call_args.kwargs["context"] is not None
