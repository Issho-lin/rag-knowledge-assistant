"""通用图抽取模型：实体、关系及其来源证据。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphEntity(BaseModel):
    id: str
    type: str = "Entity"
    properties: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    evidence: str = ""
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class GraphRelation(BaseModel):
    source_id: str
    source_type: str = "Entity"
    relation: str
    target_id: str
    target_type: str = "Entity"
    properties: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    evidence: str = ""
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    extractor: str = "llm"


class GraphDocument(BaseModel):
    source: str
    file_hash: str = ""
    entities: list[GraphEntity] = Field(default_factory=list)
    relations: list[GraphRelation] = Field(default_factory=list)

