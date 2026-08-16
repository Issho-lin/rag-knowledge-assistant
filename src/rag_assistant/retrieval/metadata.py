"""Chunk 元数据：领域推断与检索结果补全。

入库时写入 Chroma / BM25，供检索后按 domain / corpus 等过滤。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# 文件名关键词 → domain（分库预演；第 8 周会迁入 Profile）
_DOMAIN_RULES: list[tuple[tuple[str, ...], str]] = [
    (("请假", "考勤", "报销", "差旅", "员工手册"), "hr"),
    (("IT", "账号", "信息安全", "数据分级"), "it_sec"),
    (("FAQ", "行政", "入职", "发布", "协作", "产品"), "ops"),
]


def infer_domain(source: str, *, kind: str = "") -> str:
    """根据文件路径与类型推断领域标签。"""
    if kind == "csv" or source.lower().endswith(".csv"):
        return "tabular"
    name = Path(source).name
    for keywords, domain in _DOMAIN_RULES:
        if any(kw in name for kw in keywords):
            return domain
    return "general"


def build_chunk_metadata(
    *,
    source: str,
    kind: str,
    corpus: str,
    kb: str,
    parent_text: str,
    chunk_index: int,
    doc_id: str = "",
    file_hash: str = "",
) -> dict[str, str | int]:
    """入库时写入向量库 / BM25 的元数据。"""
    meta: dict[str, str | int] = {
        "source": source,
        "kind": kind,
        "corpus": corpus,
        "kb": kb,
        # 推断领域-目前没有什么用处，先预留
        "domain": infer_domain(source, kind=kind),
        # 父文本
        "parent_text": parent_text,
        # 块索引
        "chunk_index": chunk_index,
    }
    if doc_id:
        meta["doc_id"] = doc_id
    if file_hash:
        meta["file_hash"] = file_hash
    return meta


def chunk_from_hit(meta: dict[str, Any], *, text: str, doc_id: str, score: float) -> dict[str, Any]:
    """把向量库 / BM25 命中整理成 pipeline 统一 chunk 结构。"""
    source = str(meta.get("source", "?"))
    return {
        "id": doc_id,
        "text": text,
        "source": source,
        "score": score,
        "kind": meta.get("kind", ""),
        "corpus": meta.get("corpus", ""),
        "kb": meta.get("kb", ""),
        "domain": meta.get("domain", infer_domain(source, kind=str(meta.get("kind", "")))),
        "parent_text": meta.get("parent_text", ""),
        "chunk_index": meta.get("chunk_index", -1),
    }
