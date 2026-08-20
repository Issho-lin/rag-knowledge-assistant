"""知识库注册表：每个 KB 对应一个 ReAct 工具（tool_name + description 供 Agent 选型）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..ingest.loaders import Document
from .profiles import COMMON_PROFILE, KBProfile, PDF_PROFILE, POLICIES_PROFILE, TABULAR_PROFILE

# vector=Qdrant/Chroma+BM25；graph=Neo4j，不写向量库
KBBackend = Literal["vector", "graph"]


@dataclass(frozen=True)
class KnowledgeBase:
    id: str
    name: str
    profile: KBProfile  # 检索/切块策略，经 retrieve_chunks 合并
    tool_name: str  # LangChain StructuredTool.name，如 search_policies
    description: str  # 写入工具 description，供 Agent 理解边界
    corpus_names: tuple[str, ...] = ()  # 空 = 由 resolve_kb_id 按文档类型路由
    backend: KBBackend = "vector"


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
    if corpus == "kb_graph":
        return "relations"
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
        description=(
            "公司制度、FAQ、SOP、IT/安全/差旅/入职等在线 MD/HTML 文档。"
            "不适用：表格行数据、PDF 手册、汇报线/服务依赖/审批链（用 query_relations）。"
        ),
        corpus_names=("internal",),
    ),
    "tabular": KnowledgeBase(
        id="tabular",
        name="表格数据",
        profile=TABULAR_PROFILE,
        tool_name="search_tabular",
        description=(
            "按行存储的结构化表格（CSV 等），适合工号/分机/邮箱等字段精确匹配。"
            "不适用：谁向谁汇报、隔级上级、系统依赖链（用 query_relations）。"
        ),
        corpus_names=("internal",),
    ),
    "pdf": KnowledgeBase(
        id="pdf",
        name="PDF 手册",
        profile=PDF_PROFILE,
        tool_name="search_pdf_handbook",
        description=(
            "PDF 手册：办公设备操作、园区后勤与设施（访客临停费率、停车场、餐厅、健身中心等）。"
            "不适用：在线 MD/HTML 制度文档。"
        ),
        corpus_names=("kb_pdf",),
    ),
    "relations": KnowledgeBase(
        id="relations",
        name="关系图谱",
        profile=COMMON_PROFILE,
        tool_name="query_relations",
        description=(
            "组织汇报线、隔级上级、系统/服务依赖、审批链等多跳关系。"
            "问「谁的上级」「A 依赖什么」「报销审批有哪些环节」时用本工具。"
            "不适用：年假天数、报销额度等制度条文，也不适用于工号分机查询。"
        ),
        corpus_names=("kb_graph",),
        backend="graph",
    ),
}


def get_kb(kb_id: str) -> KnowledgeBase:
    """根据知识库 ID 获取知识库配置。"""
    if kb_id not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"未知 kb_id={kb_id!r}，可选: {known}")
    return _REGISTRY[kb_id]


def get_kb_by_tool_name(tool_name: str) -> KnowledgeBase:
    """根据 Agent 工具名反查 KB。"""
    for kb in _REGISTRY.values():
        if kb.tool_name == tool_name:
            return kb
    known = ", ".join(sorted(kb.tool_name for kb in _REGISTRY.values()))
    raise KeyError(f"未知 tool_name={tool_name!r}，可选: {known}")


def list_kbs() -> list[KnowledgeBase]:
    """获取所有知识库配置；``build_kb_tools`` 据此生成 ReAct 工具列表。"""
    return list(_REGISTRY.values())


def list_vector_kbs() -> list[KnowledgeBase]:
    """仅向量/BM25 物理库（ingest 与跨库检索用；排除 Neo4j）。"""
    return [kb for kb in list_kbs() if kb.backend == "vector"]


def kb_profile_for_doc(doc: Document) -> KBProfile:
    """根据文档类型选切块/检索策略"""
    return get_kb(resolve_kb_id(doc)).profile
