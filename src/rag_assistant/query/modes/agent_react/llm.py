"""--react ReAct 用 LLM：需同时承担选型、读 Observation、写终答，故用 strong 模型。"""

from langchain_openai import ChatOpenAI

from ....core.config import get_settings


def react_llm() -> ChatOpenAI:
    """构造 LangChain ChatOpenAI，供 ``create_agent`` 绑定工具。"""
    s = get_settings()  # 单例配置对象
    return ChatOpenAI(
        model=s.chat_model_strong,  # ReAct 用强模型（选型+综合+作答）
        timeout=s.llm_timeout_seconds,  # 单次请求超时，防挂死
        max_retries=0,  # 失败不自动重试，便于本地调试看到真实错误
        api_key=s.openai_api_key,  # OpenAI 或兼容网关的 Key
        base_url=s.openai_base_url,  # 兼容 OneAPI、DeepSeek 等 OpenAI 格式网关
    )
