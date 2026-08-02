"""统一向量库与 BM25 索引路径（入库与检索共用）。"""

from pathlib import Path

UNIFIED_CHROMA = Path("data/chroma/unified")
BM25_PATH = UNIFIED_CHROMA / "bm25.pkl"
