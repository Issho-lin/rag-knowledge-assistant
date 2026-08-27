"""问句 → 通用 GraphPlan；不让模型生成或执行任意 Cypher。"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.llm import LLMClient
from ..core.logging import get_logger
log = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class GraphPlan(BaseModel):
    """与业务领域无关的图查询计划。"""

    model_config = ConfigDict(extra="forbid")

    intent: Literal[
        "entity_lookup",
        "relationship_lookup",
        "path_search",
        "neighborhood",
        "attribute_lookup",
    ] = "neighborhood"
    entities: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)
    target_entity_types: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    direction: Literal["outgoing", "incoming", "both"] = "both"
    min_hops: int = Field(1, ge=0, le=3)
    max_hops: int = Field(1, ge=1, le=3)
    filters: dict[str, Any] = Field(default_factory=dict)
    return_fields: list[str] = Field(default_factory=list)
    limit: int = Field(20, ge=1, le=100)

    @field_validator("min_hops", mode="before")
    @classmethod
    def _normalize_min_hops(cls, v: Any) -> int:
        return min(max(int(v or 0), 0), 3)

    @field_validator("max_hops", mode="before")
    @classmethod
    def _cap_max_hops(cls, v: Any) -> int:
        return min(max(int(v or 1), 1), 3)

    @field_validator(
        "entities",
        "entity_types",
        "target_entity_types",
        "relation_types",
        "return_fields",
        mode="before",
    )
    @classmethod
    def _none_to_list(cls, v: Any) -> list:
        return [] if v is None else v

    @field_validator("filters", mode="before")
    @classmethod
    def _none_to_dict(cls, v: Any) -> dict:
        return {} if v is None or v == [] else v

def parse_plan_payload(raw: str) -> GraphPlan:
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    data = json.loads(text)
    return GraphPlan.model_validate(data)


def plan_graph_query(question: str, *, catalog: dict[str, Any]) -> GraphPlan:
    """用模型把问句编成受约束 GraphPlan；失败显式抛错，不猜业务关系。"""
    system = f"""你是通用图查询规划器。只输出 JSON，不要解释。
图中实体和关系由文档自动抽取，不要假设只有某个固定业务领域。
可用查询意图：entity_lookup, relationship_lookup, path_search, neighborhood, attribute_lookup。
意图边界：
- entity_lookup：只确认实体本身、类型或是否存在
- attribute_lookup：查询/过滤实体属性
- relationship_lookup：查询实体直接连接的组成、成员、环节或关系
- path_search：查询间接关系、先后顺序或多跳路径
- neighborhood：开放式查看实体周边关系
已知实体目录和关系类型（优先从中选择，不要发明）：{catalog}

JSON 字段：
- intent: 上述查询意图
- entities: 问题涉及的实体名称列表，按起点、终点顺序
- entity_types: 起点实体类型；实体/属性查询时表示待查询类型
- target_entity_types: 关系或路径终点类型；未知时为空
- relation_types: 问题涉及的关系名称；未知时为空
- direction: outgoing | incoming | both
- min_hops / max_hops: 0-3 / 1-3 整数；实体查询使用 0/1
- filters: 属性过滤条件
- return_fields: 需要返回的属性名
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
        raise
    if plan.min_hops > plan.max_hops:
        plan = plan.model_copy(update={"min_hops": plan.max_hops})
    log.info(
        "graph.plan",
        intent=plan.intent,
        hops=f"{plan.min_hops}..{plan.max_hops}",
        entities=plan.entities,
    )
    return plan
