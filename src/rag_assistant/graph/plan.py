"""问句 → 结构化 GraphPlan → 仅执行参数化 Cypher 模板（禁止 Text2Cypher 直接跑）。"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from ..core.llm import LLMClient
from ..core.logging import get_logger
from .schema import HOP2_HINTS, PATTERN_LEXICON, Pattern, SCHEMA_CARD

log = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class GraphPlan(BaseModel):
    """图查询计划：只允许枚举模式 + 已链接实体，hops 有上限。"""

    pattern: Pattern
    entity: str | None = None
    hops: int = Field(1, ge=1, le=3)
    exact_hops: bool = False
    process: str | None = None

    @field_validator("hops")
    @classmethod
    def _cap_hops(cls, v: int) -> int:
        return min(max(int(v), 1), 3)


def infer_plan_from_lexicon(question: str) -> GraphPlan:
    """LLM 不可用时的本体词典降级，不绑定具体流程名或人名。"""
    hops = 2 if any(h in question for h in HOP2_HINTS) else 1
    exact = hops == 2 and any(h in question for h in ("隔级", "上级的上级", "两级"))
    for pattern, keys in PATTERN_LEXICON.items():
        if any(k in question for k in keys):
            return GraphPlan(pattern=pattern, hops=hops, exact_hops=exact)
    return GraphPlan(pattern="neighborhood", hops=hops)


def parse_plan_payload(raw: str) -> GraphPlan:
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    data = json.loads(text)
    return GraphPlan.model_validate(data)


def plan_graph_query(question: str, *, catalog: dict[str, list[str]]) -> GraphPlan:
    """用便宜模型把问句编成 GraphPlan；失败则词典降级。"""
    system = f"""你是图查询规划器。只输出 JSON，不要解释。
{SCHEMA_CARD}
已知实体（优先从中选 entity / process，不要发明）：
Person: {catalog.get("people", [])}
Service: {catalog.get("services", [])}
Process: {catalog.get("processes", [])}

JSON 字段：
- pattern: reports_to | depends_on | approval_chain | neighborhood
- entity: 人名或服务名，approval_chain 可为空
- hops: 1-3 整数。隔级/间接/两级用 2
- exact_hops: 隔级上级为 true（恰好 N 跳）；间接依赖为 false（1..N）
- process: 审批链的 process 名，未知则 null
"""
    try:
        raw = LLMClient().invoke(
            [SystemMessage(content=system), HumanMessage(content=question)],
            tier="cheap",
        )
        plan = parse_plan_payload(raw)
    except Exception as exc:
        log.warning("graph.plan_llm_failed", error=str(exc)[:200])
        plan = infer_plan_from_lexicon(question)
    log.info("graph.plan", pattern=plan.pattern, hops=plan.hops, entity=plan.entity)
    return plan
