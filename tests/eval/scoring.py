"""eval 纯打分逻辑（无 LLM），供 run.py 与 pytest 复用。"""

from __future__ import annotations

from pathlib import Path

from rag_assistant.refusal import is_refusal, normalize_for_match


def normalize(text: str) -> str:
    """比对前去掉半角/全角空格，避免「5 天」与「5天」误伤。"""
    return normalize_for_match(text)


def format_rule(rule: str | list) -> str:
    if isinstance(rule, str):
        return rule
    return f"({'|'.join(rule)})"


def contains_normalized(haystack: str, needle: str) -> bool:
    return normalize(needle) in normalize(haystack)


def rule_hit(answer: str, rule: str | list) -> str | None:
    """命中则返回 golden 里写的词，否则 None。"""
    if isinstance(rule, str):
        return rule if contains_normalized(answer, rule) else None
    for kw in rule:
        if contains_normalized(answer, kw):
            return kw
    return None


def score_answer(answer: str, item: dict) -> dict:
    must = item.get("must_contain") or []
    hits: list[str] = []
    miss: list[str] = []
    for rule in must:
        matched = rule_hit(answer, rule)
        if matched is not None:
            hits.append(matched)
        else:
            miss.append(format_rule(rule))
    ratio = (len(hits) / len(must)) if must else 0.0
    refuse_ok = True
    if item.get("expect_refuse"):
        refuse_ok = is_refusal(answer)
    passed = ratio >= 1.0 and refuse_ok
    return {
        "keyword_hits": hits,
        "keyword_miss": miss,
        "keyword_score": round(ratio, 3),
        "refuse_ok": refuse_ok,
        "passed": passed,
    }


def score_recall(chunks: list[dict], item: dict) -> dict | None:
    """检索 recall@k：expected_sources 是否都在 top-k 结果里出现。"""
    expected = item.get("expected_sources") or []
    if not expected:
        return None

    retrieved_paths = [c["source"] for c in chunks]
    retrieved_names = list(dict.fromkeys(Path(p).name for p in retrieved_paths))

    miss: list[str] = []
    for exp in expected:
        if not any(exp in path for path in retrieved_paths):
            miss.append(exp)

    return {
        "expected_sources": expected,
        "retrieved_sources": retrieved_names,
        "recall_hit": len(miss) == 0,
        "recall_miss": miss,
    }
