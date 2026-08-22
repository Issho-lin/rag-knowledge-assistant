"""LLM 通用实体关系抽取：输出 GraphDocument，不把领域关系写死。"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.llm import LLMClient
from ..core.logging import get_logger
from .extract import Triple
from .models import GraphDocument, GraphEntity, GraphRelation

log = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_SYSTEM = """从文档中抽取知识图谱。只输出 JSON，不要解释。
自动识别文档中明确出现的实体、实体类型、实体属性、关系和关系属性。
不要编造文档中没有的事实，不要把推理结论当成直接事实。
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


def extract_triples_with_llm(text: str, source: str) -> list[Triple]:
    """对整篇 prose 做一次结构化抽取；调用失败返回空列表。"""
    if not text.strip():
        return []
    try:
        raw = LLMClient().invoke(
            [
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=text[:8000]),
            ],
            tier="cheap",
        )
        payload = _parse_json(raw)
    except Exception as exc:
        log.warning("graph.llm_extract_failed", source=source, error=str(exc)[:200])
        return []

    triples: list[Triple] = []
    for item in payload.get("triples") or []:
        rel = str(item.get("rel") or "").strip()
        src = str(item.get("src") or "").strip()
        dst = str(item.get("dst") or "").strip()
        if rel not in ALLOWED_RELS or not src or not dst:
            continue
        if rel == "NEXT_STEP":
            continue  # 审批链由有序列表规则抽，避免 LLM 把环节顺序抽乱
        triples.append(Triple(rel, src, dst, source, {}, extractor="llm"))
    log.info("graph.llm_extract_done", source=source, n=len(triples))
    return triples


def extract_graph_document_with_llm(
    text: str,
    source: str,
    *,
    file_hash: str = "",
) -> GraphDocument:
    """按文章中的 GraphDocument 形态抽取任意领域实体和关系。"""
    if not text.strip():
        return GraphDocument(source=source, file_hash=file_hash)
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
            file_hash=file_hash,
            entities=entities,
            relations=relations,
        )
    except Exception as exc:
        log.warning("graph.llm_graph_extract_failed", source=source, error=str(exc)[:200])
        return GraphDocument(source=source, file_hash=file_hash)
