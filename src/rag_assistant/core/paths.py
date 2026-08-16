"""向量库与 BM25 路径（物理分库：每 KB 独立目录 / collection / index）。"""

from pathlib import Path

CHROMA_ROOT = Path("data/chroma")
# 逻辑分库遗留路径（reset 时一并清理）
UNIFIED_CHROMA = CHROMA_ROOT / "unified"
BM25_PATH = UNIFIED_CHROMA / "bm25.pkl"


def chroma_path_for_kb(kb_id: str) -> Path:
    return CHROMA_ROOT / kb_id


def bm25_path_for_kb(kb_id: str) -> Path:
    return chroma_path_for_kb(kb_id) / "bm25.pkl"
