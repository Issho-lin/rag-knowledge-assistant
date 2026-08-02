"""Function calling 路由：只选型，不执行检索。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ....kb.registry import get_kb_by_tool_name
from ....kb.search import build_kb_tools
from ....core.logging import get_logger
from .llm import router_llm
from .prompts import ROUTER_SYSTEM

log = get_logger(__name__)


def select_tool_names(question: str, *, max_tools: int = 1) -> list[str]:
    """用 function calling 选出要调用的工具名（不执行检索）。"""
    tools = build_kb_tools()
    llm = router_llm().bind_tools(tools)
    resp = llm.invoke(
        [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=question),
        ]
    )
    if not resp.tool_calls:
        log.warning("agent.no_tool_call", question=question[:80])
        return []

    names: list[str] = []
    for call in resp.tool_calls[:max_tools]:
        if isinstance(call, dict):
            name = call.get("name")
        else:
            name = getattr(call, "name", None)
        if name and name not in names:
            names.append(name)
    log.info("agent.tool_selected", tools=names, question=question[:80])
    return names


def resolve_tool_to_kb_id(tool_name: str) -> str:
    return get_kb_by_tool_name(tool_name).id
