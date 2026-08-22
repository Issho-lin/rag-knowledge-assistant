"""问句 → 结构化 GraphPlan → 仅执行参数化 Cypher 模板（禁止 Text2Cypher 直接跑）。"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from ..core.llm import LLMClient
from ..core.logging import get_logger
from .schema import HOP2_HINTS, PATTERN_LEXICON, Pattern, SCHEMA_CARD

log = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class GraphPlan(BaseModel):
    """通用图查询计划；保留 pattern 兼容旧领域查询。"""

    intent: Literal[
        "entity_lookup",
        "relationship_lookup",
        "path_search",
        "neighborhood",
        "attribute_lookup",
    ] = "neighborhood"
    pattern: str = "neighborhood"
    entity: str | None = None
    entities: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    direction: Literal["outgoing", "incoming", "both"] = "both"
    hops: int = Field(1, ge=1, le=3)
    min_hops: int = Field(1, ge=1, le=3)
    max_hops: int = Field(1, ge=1, le=3)
    exact_hops: bool = False
    process: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    return_fields: list[str] = Field(default_factory=list)
    limit: int = Field(20, ge=1, le=100)

    @field_validator("hops")
    @classmethod
    def _cap_hops(cls, v: int) -> int:
        return min(max(int(v), 1), 3)

    @field_validator("max_hops")
    @classmethod
    def _cap_max_hops(cls, v: int) -> int:
        return min(max(int(v), 1), 3)

    @field_validator("entities", "relation_types", "return_fields", mode="before")
    @classmethod
    def _none_to_list(cls, v: Any) -> list:
        return [] if v is None else v

    @field_validator("filters", mode="before")
    @classmethod
    def _none_to_dict(cls, v: Any) -> dict:
        return {} if v is None else v


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
    system = f"""你是通用图查询规划器。只输出 JSON，不要解释。
图中实体和关系由文档自动抽取，不要假设只有某个固定业务领域。
可用查询意图：entity_lookup, relationship_lookup, path_search,
neighborhood, attribute_lookup。
已知实体目录（优先从中选择，不要发明）：{catalog}

JSON 字段：
- intent: 上述查询意图
- entities: 问题涉及的实体名称列表
- relation_types: 问题涉及的关系名称；未知时为空
- direction: outgoing | incoming | both
- min_hops / max_hops: 1-3 整数
- pattern: 兼容旧数据时可填 reports_to / depends_on / approval_chain / neighborhood
- entity: 兼容旧调用时填写第一个实体
- exact_hops: 是否恰好固定跳数
- filters: 属性过滤条件
- limit: 1-100
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
    # 跳数是安全和正确性关键：明确的“隔级/两跳”不能被模型的默认 1 覆盖。
    lexical = infer_plan_from_lexicon(question)
    if lexical.hops >= 2:
        plan = plan.model_copy(
            update={
                "hops": lexical.hops,
                "min_hops": lexical.hops if lexical.exact_hops else 1,
                "max_hops": lexical.hops,
                "exact_hops": lexical.exact_hops,
            }
        )
    if plan.pattern == "neighborhood" and lexical.pattern != "neighborhood":
        plan = plan.model_copy(update={"pattern": lexical.pattern})
    log.info("graph.plan", pattern=plan.pattern, hops=plan.hops, entity=plan.entity)
    return plan
