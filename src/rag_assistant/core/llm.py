"""具备韧性的 LLM 客户端。"""

from __future__ import annotations

import time

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from .config import get_settings
from .exceptions import NonRetryableLLMError, RetryableLLMError

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class LLMClient:
    """封装 ChatOpenAI：超时、精确重试、强弱模型降级。"""

    def __init__(self) -> None:
        s = get_settings()
        self._max_retries = s.llm_max_retries
        self._strong = self._make(s.chat_model_strong, s)
        self._cheap = self._make(s.chat_model_cheap, s)

    @staticmethod
    def _make(model: str, s) -> ChatOpenAI:
        return ChatOpenAI(
            model=model,
            timeout=s.llm_timeout_seconds,
            max_retries=0,
            api_key=s.openai_api_key,
            base_url=s.openai_base_url,
        )

    def classify(self, exc: Exception) -> None:
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        if status is not None and status not in _RETRYABLE_STATUS:
            raise NonRetryableLLMError(str(exc)) from exc
        if status is not None or isinstance(exc, TimeoutError):
            raise RetryableLLMError(str(exc)) from exc
        raise RetryableLLMError(str(exc)) from exc

    def _call_once(self, model: ChatOpenAI, messages: list[BaseMessage]) -> str:
        try:
            resp = model.invoke(messages)
        except Exception as exc:
            self.classify(exc)
            raise
        return resp.content if hasattr(resp, "content") else str(resp)

    def _call_with_retries(self, model: ChatOpenAI, messages: list[BaseMessage]) -> str:
        wait_seconds = 1.0
        last_error: RetryableLLMError | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                return self._call_once(model, messages)
            except NonRetryableLLMError:
                raise
            except RetryableLLMError as err:
                last_error = err
                if attempt == self._max_retries:
                    break
                time.sleep(wait_seconds)
                wait_seconds = min(wait_seconds * 2, 20.0)

        if last_error is None:
            raise RetryableLLMError("LLM 调用失败，且未捕获到具体错误")
        raise last_error

    def invoke(self, messages: list[BaseMessage], *, tier: str = "strong") -> str:
        primary = self._strong if tier == "strong" else self._cheap
        fallback = self._cheap if tier == "strong" else None

        try:
            return self._call_with_retries(primary, messages)
        except NonRetryableLLMError:
            raise
        except RetryableLLMError:
            if fallback is None or fallback is primary:
                raise
            return self._call_with_retries(fallback, messages)
