"""从环境变量 / .env 加载的类型化应用配置。

密钥绝不硬编码。所有配置都走这里，保证模型、网关、可靠性参数只有一处真相来源。
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- LLM 网关（OpenAI 兼容协议）----
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="OPENAI_BASE_URL")

    # 模型分级：简单任务用便宜模型，难推理用强模型
    chat_model_strong: str = Field("gpt-4o", alias="CHAT_MODEL_STRONG")
    chat_model_cheap: str = Field("gpt-4o-mini", alias="CHAT_MODEL_CHEAP")
    embedding_model: str = Field("text-embedding-3-small", alias="EMBEDDING_MODEL")

    # ---- 可靠性 ----
    llm_timeout_seconds: int = Field(30, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(4, alias="LLM_MAX_RETRIES")

    # ---- 可观测性 ----
    langfuse_public_key: str | None = Field(None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(None, alias="LANGFUSE_SECRET_KEY")
    # SDK 优先读 base_url；host 为旧别名，二者填一即可
    langfuse_base_url: str | None = Field(None, alias="LANGFUSE_BASE_URL")
    langfuse_host: str = Field("https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # ---- 重排 ----
    # cross-encoder；空或未启用时跳过。首次加载会下载模型。
    rerank_model: str = Field("BAAI/bge-reranker-base", alias="RERANK_MODEL")
    rerank_enabled: bool = Field(True, alias="RERANK_ENABLED")

    # ---- 拒答（Week 5）----
    # 重排启用时：cross-encoder top-1 低于此值则直接拒答（不调 LLM）
    refuse_min_rerank_score: float = Field(0.15, alias="REFUSE_MIN_RERANK_SCORE")
    # 仅向量 / 非 RRF 分数时：余弦相似度 top-1 低于此值则拒答
    refuse_min_vector_score: float = Field(0.35, alias="REFUSE_MIN_VECTOR_SCORE")

    # ---- 存储 / 语料 ----
    # 知识库父目录：其下每个子目录（含 markdown/html/csv）都会被统一入库、统一检索
    corpus_dir: Path = Field(Path("./data/corpus"), alias="CORPUS_DIR")
    # 统一向量库默认路径（pipeline 实际使用 data/chroma/unified）
    chroma_path: Path = Field(Path("./data/chroma/unified"), alias="CHROMA_PATH")


_settings: Settings | None = None


def get_settings() -> Settings:
    """缓存单例；仅首次调用时读取环境变量。"""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
