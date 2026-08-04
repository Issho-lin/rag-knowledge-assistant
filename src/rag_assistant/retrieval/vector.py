"""向量库入口（生产：Qdrant；CI/离线：Chroma）。"""

from .vector_store import VectorStore, create_vector_store

__all__ = ["VectorStore", "create_vector_store"]
