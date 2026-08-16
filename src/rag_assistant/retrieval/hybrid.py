"""混合检索：向量 + BM25，用 RRF（Reciprocal Rank Fusion）融合。

RRF 不依赖两路分数同量纲，只看各自排名：score += 1 / (rrf_k + rank)。
"""

from __future__ import annotations

from typing import Any

from ..core.logging import get_logger
from .bm25_backend import BM25Backend
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

    # 初始化一个空字典，用于存储每个文档的分数
    scores: dict[str, float] = {}
    # 初始化一个空字典，用于存储每个文档的原始数据
    payload: dict[str, dict[str, Any]] = {}
    # 对每个子查询结果进行融合
    for results in ranked_lists:
        for rank, item in enumerate(results, start=1):
            doc_id = item["id"]
            # 计算每个文档的分数
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
            # 保留第一次见到的正文；附加各路原始分便于调试
            if doc_id not in payload:
                # 将每个文档的原始数据存储到 payload 中
                payload[doc_id] = dict(item)
    # 对每个文档的分数进行排序
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    # 初始化一个空列表，用于存储融合后的结果
    out: list[dict[str, Any]] = []
    for doc_id, score in fused:
        row = dict(payload[doc_id])
        row["score"] = score
        out.append(row)
        
    return out


class HybridRetriever:
    """向量召回 + BM25 召回 → RRF 融合。"""

    def __init__(self, vector: VectorStore, bm25: BM25Backend) -> None:
        # 初始化向量检索引擎
        self.vector = vector
        # 初始化 BM25 检索引擎
        self.bm25 = bm25

    def query(
        self,
        text: str,
        k: int = 4,
        *,
        fetch_k: int | None = None,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """fetch_k：每路多取一些再融合，默认 max(k*3, 12)。"""
        n = fetch_k if fetch_k is not None else max(k * 3, 12)
        vec_hits = self.vector.query(text, k=n, metadata_filter=metadata_filter)
        bm25_hits = self.bm25.query(text, k=n, metadata_filter=metadata_filter)
        # 对多个子查询结果进行融合排序，返回 top-k 条结果
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
