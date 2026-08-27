"""LLM 通用实体关系抽取：输出 GraphDocument，不把领域关系写死。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.llm import LLMClient
from ..core.logging import get_logger
from .models import GraphDocument, GraphEntity, GraphRelation

log = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_SYSTEM = """从文档中抽取知识图谱。只输出 JSON，不要解释。
自动识别文档中明确出现的实体、实体类型、实体属性、关系和关系属性。
不要编造文档中没有的事实，不要把推理结论当成直接事实。
实体类型和关系名称使用稳定、简短的英文 PascalCase / UPPER_SNAKE_CASE。
同一实体在整篇文档中必须使用相同 id 和 type。实体别名放入 properties.aliases 数组。
表格或列表明确表达先后顺序时，必须为相邻项目抽取 NEXT_STEP 关系；
不要只抽取“流程包含步骤”而丢失可查询的顺序。
格式：
{"entities":[{"id":"实体名","type":"实体类型","properties":{}}],
 "relations":[{"source_id":"实体名","source_type":"实体类型",
 "relation":"关系名称","target_id":"实体名","target_type":"实体类型",
 "properties":{},"evidence":"原文证据"}]}
"""


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


def _document_title(text: str, source: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else Path(source).stem


def extract_graph_document_with_llm(
    text: str,
    source: str,
    *,
    file_hash: str = "",
) -> GraphDocument:
    """抽取任意领域实体和关系；失败抛错，禁止静默写入空图。"""
    if not text.strip():
        return GraphDocument(
            source=source,
            title=_document_title(text, source),
            file_hash=file_hash,
        )
    try:
        raw = LLMClient().invoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=text[:12000])],
            tier="cheap",
        )
        payload = _parse_json(raw)
        entities = [
            GraphEntity(
                id=str(item.get("id") or "").strip(),
                type=str(item.get("type") or "Entity").strip() or "Entity",
                properties=item.get("properties") or {},
                source=source,
                evidence=text[:500],
            )
            for item in payload.get("entities") or []
            if str(item.get("id") or "").strip()
        ]
        relations = [
            GraphRelation(
                source_id=str(item.get("source_id") or "").strip(),
                source_type=str(item.get("source_type") or "Entity").strip(),
                relation=str(item.get("relation") or "").strip(),
                target_id=str(item.get("target_id") or "").strip(),
                target_type=str(item.get("target_type") or "Entity").strip(),
                properties=item.get("properties") or {},
                source=source,
                evidence=str(item.get("evidence") or "").strip(),
                extractor="llm",
            )
            for item in payload.get("relations") or []
            if str(item.get("source_id") or "").strip()
            and str(item.get("target_id") or "").strip()
            and str(item.get("relation") or "").strip()
        ]
        return GraphDocument(
            source=source,
            title=_document_title(text, source),
            file_hash=file_hash,
            entities=entities,
            relations=relations,
        )
    except Exception as exc:
        log.warning("graph.llm_graph_extract_failed", source=source, error=str(exc)[:200])
        raise
