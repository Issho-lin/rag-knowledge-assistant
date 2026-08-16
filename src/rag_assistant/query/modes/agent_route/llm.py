"""--agent 路由用 LLM（cheap + function calling）。"""

from langchain_openai import ChatOpenAI

from ....core.config import get_settings


def router_llm() -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        model=s.chat_model_cheap,
        timeout=s.llm_timeout_seconds,
        max_retries=0,
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
    )
