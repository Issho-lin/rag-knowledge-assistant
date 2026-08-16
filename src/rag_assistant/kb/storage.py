"""物理分库：检索 / ingest 按 KB 创建独立向量与 BM25 后端。"""

from __future__ import annotations

from ..retrieval.bm25_store import create_bm25_store
from ..retrieval.vector_store import create_vector_store
from .registry import list_kbs


def total_vector_count() -> int:
    """全部 KB 向量库 chunk 总数（用于入库校验与空库检测）。"""
    return sum(create_vector_store(kb_id=kb.id).count() for kb in list_kbs())


def total_bm25_count() -> int:
    return sum(create_bm25_store(kb_id=kb.id).count() for kb in list_kbs())
