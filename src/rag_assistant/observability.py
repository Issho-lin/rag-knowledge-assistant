"""Langfuse 可观测：可选启用，无密钥时静默跳过。

Week 2：能在控制台看到一次问答的 retrieve chunks / generate 输入输出与耗时。
"""

from __future__ import annotations

from typing import Any

from .config import get_settings
from .logging import get_logger

log = get_logger(__name__)

_client: Any | None = None
_initialized = False


def get_langfuse():
    """返回已配置的 Langfuse 客户端；未配置密钥时返回 None。"""
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True

    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        log.info("langfuse.disabled", reason="missing keys")
        _client = None
        return None

    from langfuse import Langfuse

    _client = Langfuse(
        public_key=s.langfuse_public_key,
        secret_key=s.langfuse_secret_key,
        base_url=s.langfuse_base_url or s.langfuse_host,
    )
    log.info("langfuse.enabled", host=s.langfuse_base_url or s.langfuse_host)
    return _client


def flush_langfuse() -> None:
    client = get_langfuse()
    if client is not None:
        client.flush()
