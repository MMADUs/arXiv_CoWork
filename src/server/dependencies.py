# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from rag.db.config.interface import DatabaseProvider
from rag.service.arxiv import ArxivClient
from rag.service.cache.interface import CacheProvider
from rag.service.elasticsearch.config.client import ElasticsearchClient
from rag.service.embedding.config.interface import EmbeddingProvider
from rag.service.llm.interface import LLMProvider
from rag.service.reranker.interface import RerankerProvider
from rag.service.storage.interface import StorageProvider


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """
    FastAPI dependency for DB sessions.
    """
    database: DatabaseProvider | None = getattr(request.app.state, "database", None)

    if database is None:
        raise RuntimeError("Database is not initialized on app.state")

    with database.get_session() as session:
        yield session


def get_cache_provider(request: Request) -> CacheProvider:
    cache_provider: CacheProvider | None = getattr(
        request.app.state, "cache_provider", None
    )

    if cache_provider is None:
        raise RuntimeError("cache_provider is not initialized on app.state")

    return cache_provider


def get_elasticsearch_client(request: Request) -> ElasticsearchClient:
    elasticsearch_client: ElasticsearchClient | None = getattr(
        request.app.state, "elasticsearch_client", None
    )

    if elasticsearch_client is None:
        raise RuntimeError("Elasticsearch client is not initialized on app.state")

    return elasticsearch_client


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    embedding_provider: EmbeddingProvider | None = getattr(
        request.app.state, "embedding_provider", None
    )

    if embedding_provider is None:
        raise RuntimeError("Embedding provider is not initialized on app.state")

    return embedding_provider


def get_llm_provider(request: Request) -> LLMProvider:
    llm_provider: LLMProvider | None = getattr(request.app.state, "llm_provider", None)

    if llm_provider is None:
        raise RuntimeError("llm_provider is not initialized on app.state")

    return llm_provider


def get_reranker_provider(request: Request) -> RerankerProvider:
    reranker_provider: RerankerProvider | None = getattr(
        request.app.state, "reranker_provider", None
    )

    if reranker_provider is None:
        raise RuntimeError("reranker_provider is not initialized on app.state")

    return reranker_provider


def get_optional_reranker_provider(request: Request) -> RerankerProvider | None:
    return getattr(request.app.state, "reranker_provider", None)


def get_s3_storage(request: Request) -> StorageProvider:
    storage: StorageProvider | None = getattr(request.app.state, "s3_storage", None)

    if storage is None:
        raise RuntimeError("S3 storage is not initialized on app.state")

    return storage


def get_arxiv_client(request: Request) -> ArxivClient:
    arxiv_client: ArxivClient | None = getattr(request.app.state, "arxiv_client", None)

    if arxiv_client is None:
        raise RuntimeError("arxiv_client is not initialized on app.state")

    return arxiv_client
