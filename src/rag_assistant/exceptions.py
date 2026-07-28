"""异常分层。

AI 场景下 LLM 调用的失败形态和普通代码不同。拆开错误类型，是为了让
llm.py 里的重试 / 降级能精确处理，而不是一把 `except Exception`。

  Retryable    → 瞬时：限流、超时、5xx。值得退避重试。
  NonRetryable → 永久：参数错、鉴权失败、请求畸形。重试只会浪费钱。
  AppError     → 我们自己的业务/逻辑错误，与模型服务商无关。
"""

from __future__ import annotations


class AppError(Exception):
    """应用层错误基类。"""


class LLMError(AppError):
    """LLM 服务商层错误基类。"""


class RetryableLLMError(LLMError):
    """瞬时错误：限流、超时、服务端故障。应退避重试。"""


class NonRetryableLLMError(LLMError):
    """永久错误：鉴权失败、非法请求、参数错误。不要重试。"""


class ParseError(AppError):
    """模型返回内容无法解析（例如 JSON 格式损坏）。"""
