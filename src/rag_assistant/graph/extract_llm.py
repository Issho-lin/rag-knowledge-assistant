"""LLM 补抽：只允许本体里的关系类型；失败则跳过，不阻断规则 ETL。"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.llm import LLMClient
from ..core.logging import get_logger
from .extract import Triple
from .schema import ALLOWED_RELS, SCHEMA_CARD

log = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_SYSTEM = f"""你从企业内部文档中抽取知识图谱三元组。只输出 JSON，不要解释。
允许的关系类型：{sorted(ALLOWED_RELS)}
{SCHEMA_CARD}
格式：
{{"triples":[{{"rel":"REPORTS_TO","src":"姓名或工号","dst":"姓名或工号"}},{{"rel":"DEPENDS_ON","src":"服务A","dst":"服务B"}}]}}
规则：
- 只抽文档里明确写出的直接关系，不要推断隔级/间接依赖。
- 表格里已经能看出来的边可以省略（下游会与规则结果去重）。
- 不要编造人员或服务。
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
