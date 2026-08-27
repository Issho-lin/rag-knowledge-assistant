"""CRAG 精简版：检索后相关性评估，不合格则改写 query 再检索一次。"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.llm import LLMClient
from ..core.logging import get_logger

log = get_logger(__name__)

CragGrade = Literal["correct", "incorrect", "ambiguous"]

_GRADE_SYSTEM = """你是检索质量评估器。根据用户问题与检索片段，判断证据是否足以回答。
只输出 JSON：{"grade":"correct|incorrect|ambiguous","reason":"一句中文"}。
- correct：片段直接覆盖问题关键事实
- incorrect：片段明显跑题或几乎无关
- ambiguous：部分相关但不完整，或难以判断
不要编造片段里没有的内容。"""

_REWRITE_SYSTEM = """你是检索 query 改写器。原检索结果不相关，请改写成更利于检索的短查询。
保留实体名与约束，去掉口语废话；只输出改写后的查询文本，不要解释。"""


def _preview_chunks(chunks: list[dict[str, Any]], n: int = 3, chars: int = 240) -> str:
    lines: list[str] = []
    for i, chunk in enumerate(chunks[:n], 1):
        text = str(chunk.get("text") or "").replace("\n", " ").strip()
        if len(text) > chars:
            text = text[:chars] + "…"
        lines.append(f"[{i}] {text}")
    return "\n".join(lines) if lines else "（无片段）"


def _parse_grade(raw: str) -> CragGrade:
    text = raw.strip()
    fence = re.search(r"\{[^{}]*\}", text, re.S)
    if fence:
        text = fence.group(0)
    try:
        data = json.loads(text)
        grade = str(data.get("grade", "")).lower()
        if grade in {"correct", "incorrect", "ambiguous"}:
            return grade  # type: ignore[return-value]
    except json.JSONDecodeError:
        pass
    m = re.search(r"\b(correct|incorrect|ambiguous)\b", text, re.I)
    if m:
        return m.group(1).lower()  # type: ignore[return-value]
    return "ambiguous"


def grade_retrieval(question: str, chunks: list[dict[str, Any]]) -> CragGrade:
    """评估检索结果是否足以支撑回答。无片段直接 incorrect。"""
    if not chunks:
        return "incorrect"
    user = f"问题：{question}\n\n检索片段：\n{_preview_chunks(chunks)}"
    try:
        content = LLMClient().invoke(
            [
                SystemMessage(content=_GRADE_SYSTEM),
                HumanMessage(content=user),
            ],
            tier="cheap",
        )
        grade = _parse_grade(str(content))
    except Exception as exc:  # noqa: BLE001 — 评估失败时保守放行
        log.warning("crag.grade_failed", error=str(exc))
        return "ambiguous"
    log.info("crag.grade", grade=grade, question=question[:80])
    return grade


def rewrite_query_for_crag(question: str, chunks: list[dict[str, Any]]) -> str:
    """为二次检索改写 query；失败则退回原问句。"""
    user = (
        f"原问题：{question}\n\n不相关/不足的片段：\n{_preview_chunks(chunks)}\n\n"
        "请输出改写后的检索查询："
    )
    try:
        rewritten = LLMClient().invoke(
            [
                SystemMessage(content=_REWRITE_SYSTEM),
                HumanMessage(content=user),
            ],
            tier="cheap",
        ).strip()
        rewritten = rewritten.strip("\"'` \n")
        if rewritten:
            log.info("crag.rewrite", from_q=question[:60], to_q=rewritten[:60])
            return rewritten
    except Exception as exc:  # noqa: BLE001
        log.warning("crag.rewrite_failed", error=str(exc))
    return question


def maybe_apply_crag(
    question: str,
    chunks: list[dict[str, Any]],
    *,
    retrieve_again: Callable[[str], list[dict[str, Any]]],
    enabled: bool,
) -> list[dict[str, Any]]:
    """若启用 CRAG：incorrect 时改写并 retrieve_again 一次；其余保持原结果。"""
    if not enabled:
        return chunks
    grade = grade_retrieval(question, chunks)
    if grade != "incorrect":
        return chunks
    new_q = rewrite_query_for_crag(question, chunks)
    if new_q.strip() == question.strip():
        return chunks
    second = retrieve_again(new_q)
    log.info(
        "crag.retried",
        first_n=len(chunks),
        second_n=len(second),
        query=new_q[:80],
    )
    return second if second else chunks
