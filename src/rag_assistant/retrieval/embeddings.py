"""Embedding 客户端（Chroma / Qdrant 共用）。"""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from ..core.config import get_settings
from ..core.exceptions import NonRetryableLLMError, RetryableLLMError

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


def build_embeddings() -> OpenAIEmbeddings:
    s = get_settings()
    return OpenAIEmbeddings(
        model=s.embedding_model,
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
        max_retries=0,
        check_embedding_ctx_length=False,
    )


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    embed = build_embeddings()
    try:
        return embed.embed_documents(texts)
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        if status is not None and status not in _RETRYABLE_STATUS:
            raise NonRetryableLLMError(str(exc)) from exc
        raise RetryableLLMError(str(exc)) from exc


def embedding_dimension() -> int:
    vecs = embed_documents(["dimension probe"])
    if not vecs:
        raise ValueError("embedding API returned no vectors")
    return len(vecs[0])
