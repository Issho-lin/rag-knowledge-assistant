"""向量库工厂：VECTOR_BACKEND=chroma|qdrant。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.config import get_settings
from .chroma_store import ChromaVectorStore, VectorStoreBackend
from .qdrant_store import QdrantVectorStore


def create_vector_store(*, chroma_path: Path | None = None) -> VectorStoreBackend:
    backend = get_settings().vector_backend.lower()
    if backend == "qdrant":
        return QdrantVectorStore()
    if backend != "chroma":
        raise ValueError(f"未知 VECTOR_BACKEND: {backend!r}，支持 chroma | qdrant")
    return ChromaVectorStore(chroma_path=chroma_path)


class VectorStore:
    """向后兼容：`VectorStore(chroma_path=...)` 按配置返回具体后端。"""

    def __new__(cls, chroma_path: Path | None = None, **kwargs: Any) -> VectorStoreBackend:
        if kwargs:
            raise TypeError("VectorStore 仅接受 chroma_path 参数")
        return create_vector_store(chroma_path=chroma_path)
