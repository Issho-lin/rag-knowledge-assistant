"""重排：对召回候选用 cross-encoder 精排。

召回（向量/BM25/RRF）负责「尽量找全」；重排负责「在候选里挑更相关的」。
默认模型 BAAI/bge-reranker-base（中英可用）。

国内若 HuggingFace 下不动，可用 ModelScope 预下载到本地缓存：
    uv run python -c "from modelscope import snapshot_download; print(snapshot_download('BAAI/bge-reranker-base'))"
本模块会优先加载已有的 ModelScope 缓存路径。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import get_settings
from ..logging import get_logger

log = get_logger(__name__)

_model = None


def _resolve_model_path(name: str) -> str:
    """HF id / 本地路径；若 ModelScope 已缓存同名模型则优先用本地。"""
    p = Path(name)
    if p.exists():
        return str(p)
    # modelscope snapshot_download 默认布局
    ms = (
        Path.home()
        / ".cache"
        / "modelscope"
        / "models"
        / name.replace("/", "--")
        / "snapshots"
        / "master"
    )
    if ms.is_dir():
        return str(ms)
    return name


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder

        name = get_settings().rerank_model
        resolved = _resolve_model_path(name)
        log.info("rerank.loading", model=name, resolved=resolved)
        _model = CrossEncoder(resolved)
        log.info("rerank.loaded", model=resolved)
    return _model


def rerank(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """对 chunks 按 (query, text) 相关性重排；top_k 默认保留全部排序结果。"""

    # 如果候选结果为空，则返回空列表
    if not chunks:
        return []
    # 初始化重排模型
    model = _get_model()
    # 初始化重排对（问题，候选结果）
    pairs = [(query, c["text"]) for c in chunks]
    # 对每个候选结果进行问题-结果相关性评分
    scores = model.predict(pairs)
    # 根据相关性评分排序
    ranked = sorted(
        zip(chunks, scores),
        key=lambda x: float(x[1]),
        reverse=True,
    )
    # 如果 top_k 不为空，则截取 top_k 条结果
    if top_k is not None:
        # 截取 top_k 条结果
        ranked = ranked[:top_k]
    # 初始化一个空列表，用于存储重排后的结果
    out: list[dict[str, Any]] = []
    # 对每个候选结果进行重排
    for chunk, score in ranked:
        # 将候选结果转换为字典，并附加相关性评分
        row = dict(chunk)
        row["score"] = float(score)
        # 附加重排评分
        row["rerank_score"] = float(score)
        # 将重排后的结果添加到列表中
        out.append(row)
    # 记录重排后的结果数量
    log.info(
        "rerank.done",
        candidates=len(chunks),
        top_k=len(out),
        top_score=out[0]["score"] if out else None,
    )
    return out
