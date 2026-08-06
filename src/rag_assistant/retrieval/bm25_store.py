"""BM25 工厂：BM25_BACKEND=pkl|opensearch。"""

from __future__ import annotations

from pathlib import Path

from ..core.config import get_settings
from ..core.paths import BM25_PATH
from .bm25 import BM25Store
from .bm25_backend import BM25Backend
from .opensearch_bm25 import OpenSearchBM25Store


def create_bm25_store(bm25_path: Path | None = None) -> BM25Backend:
    backend = get_settings().bm25_backend.lower()
    if backend == "opensearch":
        return OpenSearchBM25Store()
    if backend != "pkl":
        raise ValueError(f"未知 BM25_BACKEND: {backend!r}，支持 pkl | opensearch")
    return BM25Store(bm25_path if bm25_path is not None else BM25_PATH)


class BM25StoreFactory:
    """向后兼容：按配置返回 pkl 或 OpenSearch 实现。"""

    def __new__(cls, path: Path | None = None, **kwargs: object) -> BM25Backend:
        if kwargs:
            raise TypeError("BM25StoreFactory 仅接受 path 参数")
        return create_bm25_store(bm25_path=path)
