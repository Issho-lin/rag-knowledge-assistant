"""混合检索：向量 + BM25，用 RRF（Reciprocal Rank Fusion）融合。

RRF 不依赖两路分数同量纲，只看各自排名：score += 1 / (rrf_k + rank)。
"""

from __future__ import annotations

from typing import Any

from ..logging import get_logger
from .bm25 import BM25Store
from .vector import VectorStore

log = get_logger(__name__)

# 用户提问后走多路检索（向量 + BM25），各路按自己的分数排名，再用排名做 RRF 融合，把最终 top-k 交给大模型。

def rrf_fuse(
    ranked_lists: list[list[dict[str, Any]]],
    *,
    k: int = 4,
    rrf_k: int = 60,
) -> list[dict[str, Any]]:
    """按文档 id 融合多路排序结果，返回 top-k。"""
    scores: dict[str, float] = {}
    payload: dict[str, dict[str, Any]] = {}
    for results in ranked_lists:
        for rank, item in enumerate(results, start=1):
            doc_id = item["id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
            # 保留第一次见到的正文；附加各路原始分便于调试
            if doc_id not in payload:
                payload[doc_id] = dict(item)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    out: list[dict[str, Any]] = []
    for doc_id, score in fused:
        row = dict(payload[doc_id])
        row["score"] = score
        out.append(row)
    return out


class HybridRetriever:
    """向量召回 + BM25 召回 → RRF 融合。"""

    def __init__(self, vector: VectorStore, bm25: BM25Store) -> None:
        self.vector = vector
        self.bm25 = bm25

    def query(self, text: str, k: int = 4, *, fetch_k: int | None = None) -> list[dict[str, Any]]:
        """fetch_k：每路多取一些再融合，默认 max(k*3, 12)。"""
        n = fetch_k if fetch_k is not None else max(k * 3, 12)
        vec_hits = self.vector.query(text, k=n)
        bm25_hits = self.bm25.query(text, k=n)
        fused = rrf_fuse([vec_hits, bm25_hits], k=k)
        log.info(
            "retrieve.hybrid",
            k=k,
            fetch_k=n,
            vector_hits=len(vec_hits),
            bm25_hits=len(bm25_hits),
            fused=len(fused),
            top_score=fused[0]["score"] if fused else None,
        )
        return fused
