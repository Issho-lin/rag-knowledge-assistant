"""具备韧性的 LLM 客户端。

正确做法：
  - 只对瞬时错误（限流 / 超时 / 5xx）做指数退避重试；鉴权、参数错误绝不重试
  - 每次调用设超时
  - 强模型连续失败后降级到便宜模型，而不是整请求直接挂
"""

from __future__ import annotations

import time

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from .config import get_settings
from .exceptions import NonRetryableLLMError, RetryableLLMError

# 值得重试的 HTTP 状态码
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
            # 关闭 SDK 自带的「遇错就重试」，改由本类按错误类型控制
            max_retries=0,
            api_key=s.openai_api_key,
            base_url=s.openai_base_url,
        )

    def classify(self, exc: Exception) -> None:
        """把服务商异常映射到我们的异常层级，并抛出对应类型。"""
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        if status is not None and status not in _RETRYABLE_STATUS:
            raise NonRetryableLLMError(str(exc)) from exc
        if status is not None or isinstance(exc, TimeoutError):
            raise RetryableLLMError(str(exc)) from exc
        # 不确定时按瞬时错误处理，避免误杀可恢复故障
        raise RetryableLLMError(str(exc)) from exc

    def _call_once(self, model: ChatOpenAI, messages: list[BaseMessage]) -> str:
        try:
            resp = model.invoke(messages)
        except Exception as exc:
            self.classify(exc)
            raise
        return resp.content if hasattr(resp, "content") else str(resp)

    def _call_with_retries(self, model: ChatOpenAI, messages: list[BaseMessage]) -> str:
        """同一模型最多试 max_retries 次；临时错误才等待重试。"""
        wait_seconds = 1.0
        last_error: RetryableLLMError | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                return self._call_once(model, messages)
            except NonRetryableLLMError:
                # 密钥错、参数错：再试也没用，直接失败
                raise
            except RetryableLLMError as err:
                last_error = err
                is_last_try = attempt == self._max_retries
                if is_last_try:
                    break
                time.sleep(wait_seconds)
                wait_seconds = min(wait_seconds * 2, 20.0)

        # 走到这里 = 临时错误试满了仍失败
        if last_error is None:
            raise RetryableLLMError("LLM 调用失败，且未捕获到具体错误")
        raise last_error

    def invoke(self, messages: list[BaseMessage], *, tier: str = "strong") -> str:
        """调用 LLM。tier='strong' 时强模型失败可降级到便宜模型。"""
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
