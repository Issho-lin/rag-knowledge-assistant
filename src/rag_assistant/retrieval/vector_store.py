"""向量库工厂：VECTOR_BACKEND=chroma|qdrant；物理分库时 collection / 路径按 kb_id。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.paths import chroma_path_for_kb
from .chroma_store import ChromaVectorStore, VectorStoreBackend
from .qdrant_store import QdrantVectorStore


def create_vector_store(
    *,
    kb_id: str | None = None,
    chroma_path: Path | None = None,
) -> VectorStoreBackend:
    backend = get_settings().vector_backend.lower()
    if backend == "qdrant":
        collection = kb_id if kb_id is not None else get_settings().qdrant_collection
        return QdrantVectorStore(collection_name=collection)
    if backend != "chroma":
        raise ValueError(f"未知 VECTOR_BACKEND: {backend!r}，支持 chroma | qdrant")
    if chroma_path is not None:
        path = chroma_path
    elif kb_id is not None:
        path = chroma_path_for_kb(kb_id)
    else:
        path = get_settings().chroma_path
    return ChromaVectorStore(path)


class VectorStore:
    """向后兼容：`VectorStore(kb_id=...)` 或 `VectorStore(chroma_path=...)` 按配置返回具体后端。"""

    def __new__(
        cls,
        chroma_path: Path | None = None,
        kb_id: str | None = None,
        **kwargs: Any,
    ) -> VectorStoreBackend:
        if kwargs:
            raise TypeError("VectorStore 仅接受 chroma_path 或 kb_id 参数")
        return create_vector_store(kb_id=kb_id, chroma_path=chroma_path)
