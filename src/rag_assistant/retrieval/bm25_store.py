"""BM25 工厂：BM25_BACKEND=pkl|opensearch；物理分库时 index / pkl 路径按 kb_id。"""

from __future__ import annotations

from pathlib import Path

from ..core.config import get_settings
from ..core.paths import BM25_PATH, bm25_path_for_kb
from .bm25 import BM25Store
from .bm25_backend import BM25Backend
from .opensearch_bm25 import OpenSearchBM25Store


def create_bm25_store(
    bm25_path: Path | None = None,
    *,
    kb_id: str | None = None,
) -> BM25Backend:
    backend = get_settings().bm25_backend.lower()
    if backend == "opensearch":
        index = kb_id if kb_id is not None else get_settings().opensearch_index
        return OpenSearchBM25Store(index_name=index)
    if backend != "pkl":
        raise ValueError(f"未知 BM25_BACKEND: {backend!r}，支持 pkl | opensearch")
    if bm25_path is not None:
        path = bm25_path
    elif kb_id is not None:
        path = bm25_path_for_kb(kb_id)
    else:
        path = BM25_PATH
    return BM25Store(path)


class BM25StoreFactory:
    """向后兼容：按配置返回 pkl 或 OpenSearch 实现。"""

    def __new__(
        cls,
        path: Path | None = None,
        kb_id: str | None = None,
        **kwargs: object,
    ) -> BM25Backend:
        if kwargs:
            raise TypeError("BM25StoreFactory 仅接受 path 或 kb_id 参数")
        return create_bm25_store(path, kb_id=kb_id)
