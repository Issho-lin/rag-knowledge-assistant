"""子查询分解：复合问题拆成多句检索再合并。"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from ...core.llm import LLMClient
from ...core.logging import get_logger
from ...core.observability import get_langfuse

log = get_logger(__name__)

_DECOMPOSE_SYSTEM = """你是「星云科技」内部知识助手的查询分解模块。

任务：把用户问题拆成 1～3 个可独立用于文档检索的中文子问题。

规则：
1. 若已是单一主题、无需拆分，只输出包含原问题的一个 JSON 数组。
2. 若含多个并列子问题（用问号、顿号、以及、还有 等连接），按子问题拆开。
3. 每个子问题必须能独立检索，补全省略的主语。
4. 只输出 JSON 数组，如 ["子问题1", "子问题2"]，不要其它文字。"""


def _parse_subqueries(raw: str, fallback: str) -> list[str]:
    text = raw.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            items = [str(x).strip() for x in data if str(x).strip()]
            if items:
                return items
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                items = [str(x).strip() for x in data if str(x).strip()]
                if items:
                    return items
        except json.JSONDecodeError:
            pass

    parts = re.split(r"[？?]\s*", fallback)
    items = [p.strip() + "？" for p in parts if p.strip()]
    if len(items) > 1:
        return items
    return [fallback]


def decompose_for_retrieval(question: str, *, tier: str = "cheap") -> list[str]:
    """无并列子问题时返回单元素列表；失败时回退原问句。"""
    q = question.strip()
    if not q:
        return [q]

    marker_count = sum(q.count(m) for m in ("？", "?"))
    if marker_count < 2 and not any(m in q for m in ("以及", "还有")):
        return [q]

    messages = [
        SystemMessage(content=_DECOMPOSE_SYSTEM),
        HumanMessage(content=f"用户问题：{q}\n\nJSON 数组："),
    ]
    lf = get_langfuse()

    if lf is None:
        raw = LLMClient().invoke(messages, tier=tier)
    else:
        with lf.start_as_current_observation(
            name="query-decompose",
            as_type="generation",
            input={"question": q},
        ) as obs:
            raw = LLMClient().invoke(messages, tier=tier)
            obs.update(output=raw)

    subs = _parse_subqueries(raw, q)
    if len(subs) == 1 and subs[0] == q:
        log.info("decompose.unchanged", query=q)
    else:
        log.info("decompose.done", original=q, subqueries=subs)
    return subs
