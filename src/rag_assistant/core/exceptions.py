"""异常分层。"""

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
