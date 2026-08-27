"""从环境变量 / .env 加载的类型化应用配置。"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="OPENAI_BASE_URL")

    chat_model_strong: str = Field("gpt-4o", alias="CHAT_MODEL_STRONG")
    chat_model_cheap: str = Field("gpt-4o-mini", alias="CHAT_MODEL_CHEAP")
    embedding_model: str = Field("text-embedding-3-small", alias="EMBEDDING_MODEL")

    llm_timeout_seconds: int = Field(30, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(4, alias="LLM_MAX_RETRIES")

    langfuse_public_key: str | None = Field(None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(None, alias="LANGFUSE_SECRET_KEY")
    langfuse_base_url: str | None = Field(None, alias="LANGFUSE_BASE_URL")
    langfuse_host: str = Field("https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    rerank_model: str = Field("BAAI/bge-reranker-base", alias="RERANK_MODEL")
    rerank_device: str = Field("cpu", alias="RERANK_DEVICE")
    rerank_enabled: bool = Field(True, alias="RERANK_ENABLED")

    refuse_min_rerank_score: float = Field(0.15, alias="REFUSE_MIN_RERANK_SCORE")
    refuse_min_vector_score: float = Field(0.35, alias="REFUSE_MIN_VECTOR_SCORE")

    query_decompose_enabled: bool = Field(False, alias="QUERY_DECOMPOSE_ENABLED")
    parent_expand_enabled: bool = Field(False, alias="PARENT_EXPAND_ENABLED")

    corpus_dir: Path = Field(Path("./data/corpus"), alias="CORPUS_DIR")
    chroma_path: Path = Field(Path("./data/chroma/unified"), alias="CHROMA_PATH")

    # 向量库后端：chroma=CI/离线；qdrant=生产（需 docker compose up qdrant）
    vector_backend: str = Field("chroma", alias="VECTOR_BACKEND")
    qdrant_url: str = Field("http://localhost:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field("corpus", alias="QDRANT_COLLECTION")

    # BM25：pkl=CI/离线（默认）| opensearch=生产（需 docker compose up opensearch）
    bm25_backend: str = Field("pkl", alias="BM25_BACKEND")
    opensearch_url: str = Field("http://localhost:9200", alias="OPENSEARCH_URL")
    opensearch_index: str = Field("corpus", alias="OPENSEARCH_INDEX")

    # Neo4j Graph RAG（--ingest-graph / query_relations）
    neo4j_uri: str = Field("bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field("neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field("changeme", alias="NEO4J_PASSWORD")
    graph_llm_extract: bool = Field(True, alias="GRAPH_LLM_EXTRACT")
    graph_query_planner: bool = Field(True, alias="GRAPH_QUERY_PLANNER")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
