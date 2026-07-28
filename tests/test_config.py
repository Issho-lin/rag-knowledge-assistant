"""单元测试。运行：pytest -q

真正的 RAG 质量用 `tests/eval/`（golden 回归）衡量，不是这些单测。
这里只护纯函数（配置、错误分类等），且不得依赖真实 API Key 或网络。
"""

import pytest

from rag_assistant import config as config_module
from rag_assistant.exceptions import NonRetryableLLMError, RetryableLLMError
from rag_assistant.llm import LLMClient


@pytest.fixture
def fake_env(monkeypatch):
    """注入假的 key / base_url，让 Settings 可离线实例化。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")
    # 清空单例缓存，迫使用假环境重新构建
    monkeypatch.setattr(config_module, "_settings", None)
    return monkeypatch


def test_settings_singleton(fake_env):
    """get_settings 应返回同一实例（避免反复读环境）。"""
    a = config_module.get_settings()
    b = config_module.get_settings()
    assert a is b


def test_classify_retryable_on_timeout(fake_env):
    """TimeoutError → RetryableLLMError（瞬时，值得重试）。"""
    client = LLMClient()
    with pytest.raises(RetryableLLMError):
        client.classify(TimeoutError("read timed out"))


def test_classify_non_retryable_on_auth(fake_env):
    """401 鉴权错误 → NonRetryableLLMError（永久，不要浪费额度）。"""

    class FakeHTTPError(Exception):
        status_code = 401

    client = LLMClient()
    with pytest.raises(NonRetryableLLMError):
        client.classify(FakeHTTPError("invalid api key"))


def test_classify_retryable_on_rate_limit(fake_env):
    """429 限流 → RetryableLLMError（瞬时，退避后可能恢复）。"""

    class FakeHTTPError(Exception):
        status_code = 429

    client = LLMClient()
    with pytest.raises(RetryableLLMError):
        client.classify(FakeHTTPError("rate limited"))
