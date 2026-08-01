"""知识库注册表：id ↔ 语料 ↔ Profile ↔（预留）Agent 工具。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..ingest.loaders import Document
from .profiles import KBProfile, PDF_PROFILE, POLICIES_PROFILE, TABULAR_PROFILE


@dataclass(frozen=True)
class KnowledgeBase:
    id: str
    name: str
    profile: KBProfile
    tool_name: str
    description: str
    corpus_names: tuple[str, ...] = ()  # 空 = 由 resolve_kb_id 按文档类型路由


def _doc_corpus_name(doc: Document) -> str:
    """获取语料包名称。"""
    return str(doc.metadata.get("corpus", ""))


def resolve_kb_id(doc: Document) -> str:
    """入库时给文档打标签：policies / tabular / pdf"""

    # 获取语料类型
    kind = str(doc.metadata.get("kind", ""))
    # 获取语料路径
    source = doc.source.lower()
    # 获取语料包名称
    corpus = _doc_corpus_name(doc)

    # 根据语料类型和路径归入 KB
    if kind == "csv" or source.endswith(".csv"):
        return "tabular"
    if kind == "pdf" or source.endswith(".pdf"):
        return "pdf"
    if corpus == "kb_pdf":
        return "pdf"
    return "policies"


_REGISTRY: dict[str, KnowledgeBase] = {
    "policies": KnowledgeBase(
        id="policies",
        name="制度与流程文档",
        profile=POLICIES_PROFILE,
        tool_name="search_policies",
        description="公司制度、FAQ、SOP、IT/安全/差旅/入职等内部文档。不适用：表格行数据、PDF 手册。",
        corpus_names=("internal",),
    ),
    "tabular": KnowledgeBase(
        id="tabular",
        name="表格数据",
        profile=TABULAR_PROFILE,
        tool_name="search_tabular",
        description="按行存储的结构化表格（CSV 等），适合字段精确匹配。demo 语料含通讯录，亦可用于设备清单、报销明细等。",
        corpus_names=("internal",),
    ),
    "pdf": KnowledgeBase(
        id="pdf",
        name="PDF 手册",
        profile=PDF_PROFILE,
        tool_name="search_pdf_handbook",
        description="仅 PDF 格式手册与扫描件转文本。不适用：在线 MD/HTML 制度。",
        corpus_names=("kb_pdf",),
    ),
}


def get_kb(kb_id: str) -> KnowledgeBase:
    """根据知识库 ID 获取知识库配置。"""
    if kb_id not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"未知 kb_id={kb_id!r}，可选: {known}")
    return _REGISTRY[kb_id]


def list_kbs() -> list[KnowledgeBase]:
    """获取所有知识库配置。"""
    return list(_REGISTRY.values())


def kb_profile_for_doc(doc: Document) -> KBProfile:
    """根据文档类型选切块/检索策略"""
    return get_kb(resolve_kb_id(doc)).profile
