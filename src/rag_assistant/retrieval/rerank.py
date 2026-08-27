"""重排：对召回候选用 cross-encoder 精排。

召回（向量/BM25/RRF）负责「尽量找全」；重排负责「在候选里挑更相关的」。
默认模型 BAAI/bge-reranker-base（中英可用）。

国内若 HuggingFace 下不动，可用 ModelScope 预下载到本地缓存：
    uv run python -c "from modelscope import snapshot_download; print(snapshot_download('BAAI/bge-reranker-base'))"
本模块会优先加载已有的 ModelScope 缓存路径。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.logging import get_logger

log = get_logger(__name__)

_model = None
# ReAct 可能并行调多个 KB 工具；MPS/CrossEncoder 非线程安全，需串行化加载与推理。
# 使用 RLock：rerank() 持锁时 _get_model() 可重入，避免死锁。
_model_lock = threading.RLock()


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
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import CrossEncoder

            settings = get_settings()
            name = settings.rerank_model
            resolved = _resolve_model_path(name)
            device = settings.rerank_device
            log.info("rerank.loading", model=name, resolved=resolved, device=device)
            _model = CrossEncoder(resolved, device=device)
            log.info("rerank.loaded", model=resolved, device=device)
    return _model


def rerank(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """对 chunks 按 (query, text) 相关性重排；top_k 默认保留全部排序结果。"""

    if not chunks:
        return []
    pairs = [(query, c["text"]) for c in chunks]
    with _model_lock:
        model = _get_model()
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
