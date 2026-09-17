# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from rag import __version__


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "rag_answer"

    cache_ttl_seconds: int = Field(default=21600, ge=1)
    timeout_seconds: float = Field(default=2.0, gt=0)


class AgenticRAGSettings(BaseModel):
    enabled: bool = True
    max_retrieval_attempts: int = Field(default=2, ge=1, le=5)
    default_top_k: int = Field(default=8, ge=1, le=50)
    default_candidate_pool_size: int = Field(default=50, ge=1, le=500)
    use_reranker_by_default: bool = False
    enable_query_rewrite: bool = True
    weak_evidence_min_chunks: int = Field(default=2, ge=1, le=10)
    checkpoint_provider: Literal["memory", "none"] = "memory"


class CelerySettings(BaseModel):
    broker_url: str = "amqp://user:password@localhost:5672//"
    result_backend: str = "rpc://"

    pdf_download_queue: str = "paper.pdf_download"
    parsing_queue: str = "paper.parsing"
    chunking_queue: str = "paper.chunking"
    indexing_queue: str = "paper.indexing"

    pdf_download_max_retries: int = Field(default=3, ge=0)
    paper_parsing_max_retries: int = Field(default=3, ge=0)
    paper_chunking_max_retries: int = Field(default=2, ge=0)
    paper_indexing_max_retries: int = Field(default=5, ge=0)

    retry_backoff_seconds: int = Field(default=30, ge=1)
    retry_backoff_max_seconds: int = Field(default=900, ge=1)


class OllamaLLMSettings(BaseModel):
    base_url: str = "http://localhost:11434"
    model_name: str = "qwen3:8b"

    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_backoff_seconds: float = 0.5


class TransformersRerankerSettings(BaseModel):
    model_name: str = "Qwen/Qwen3-Reranker-0.6B"
    device: Literal["cpu", "cuda", "auto"] = "auto"
    max_length: int = 4096


class ElasticsearchSettings(BaseModel):
    base_url: str = "http://localhost:9200"
    chunk_index_name: str = "arxiv-papers-chunks-v1"

    vector_dimension: int = 1024
    timeout_seconds: float = 30.0

    # ES auth config (might refactor to necessary ones)
    username: str | None = None
    password: str | None = None
    api_key: str | tuple[str, str] | None = None
    verify_certs: bool = True
    ca_certs: str | None = None
    ssl_show_warn: bool = True


class OllamaEmbeddingSettings(BaseModel):
    base_url: str = "http://localhost:11434"
    model_name: str = "qwen3-embedding:0.6b"

    dimension: int = 1024
    batch_size: int = 64
    timeout_seconds: float = 25.0


class ChunkerSettings(BaseModel):
    target_chunk_words: int = 600
    max_context_words: int = 200
    overlap_words: int = 100
    min_chunk_words: int = 100
    section_based: bool = True

    @model_validator(mode="after")
    def validate_chunking_window(self) -> "ChunkerSettings":
        if self.overlap_words >= self.target_chunk_words:
            raise ValueError("overlap_words must be less than target_chunk_words")
        return self


class ParserSettings(BaseModel):
    # docling settings (primary parser)
    max_pages: int = 20
    max_file_size_mb: int = 50
    do_ocr: bool = False
    do_table_structure: bool = True
    parsing_timeout: float = 15.0

    # pymupdf fallback
    enable_fallback_parser: bool = False


class ArxivSettings(BaseModel):
    # metadata fetcher settings
    base_url: str = "https://export.arxiv.org/api/query"
    rate_limit_seconds: float = 3.0
    fetch_timeout_seconds: float = 60.0
    fetch_max_retries: int = 3
    retry_backoff_seconds: float = 2.0

    # pdf downloader settings
    download_timeout_seconds: float = 120.0
    download_max_retries: int = 3


class S3Settings(BaseModel):
    endpoint_url: str = Field(..., description="s3 endpoint url")
    access_key: str = Field(..., description="s3 access key")
    secret_key: str = Field(..., description="s3 secret key")
    region_name: str = "us-east-1"
    bucket_name: str = "arxiv-papers"


class PostgresSettings(BaseModel):
    db_url: str = Field(..., description="postgres database url")
    echo_sql: bool = False
    pool_size: int = 20
    max_overflow: int = 0

    @field_validator("db_url")
    @classmethod
    def validate_postgres_db_url(cls, value: str) -> str:
        valid_prefixes = ("postgresql://", "postgresql+psycopg://")

        if not value.startswith(valid_prefixes):
            raise ValueError(
                "db_url must start with 'postgresql://' or 'postgresql+psycopg://'"
            )

        return value


class Settings(BaseSettings):
    # application metadata
    app_name: str = "arXiv co-work"
    app_summary: str = "retrieval agent for long running paper curation"
    app_version: str = __version__

    # debug mode
    debug: bool = True

    # read .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # api settings
    api_prefix: str = "/api"

    # module settings
    arxiv_settings: ArxivSettings = Field(default_factory=ArxivSettings)
    parser_settings: ParserSettings = Field(default_factory=ParserSettings)
    chunker_settings: ChunkerSettings = Field(default_factory=ChunkerSettings)

    # infra settings
    postgres_settings: PostgresSettings = Field(default_factory=PostgresSettings)
    s3_settings: S3Settings = Field(default_factory=S3Settings)
    embedding_settings: OllamaEmbeddingSettings = Field(
        default_factory=OllamaEmbeddingSettings
    )
    elasticsearch_settings: ElasticsearchSettings = Field(
        default_factory=ElasticsearchSettings
    )
    reranker_settings: TransformersRerankerSettings = Field(
        default_factory=TransformersRerankerSettings
    )
    llm_settings: OllamaLLMSettings = Field(default_factory=OllamaLLMSettings)
    redis_settings: RedisSettings = Field(default_factory=RedisSettings)
    celery_settings: CelerySettings = Field(default_factory=CelerySettings)
    agentic_rag_settings: AgenticRAGSettings = Field(default_factory=AgenticRAGSettings)


@lru_cache
def get_settings():
    return Settings()
