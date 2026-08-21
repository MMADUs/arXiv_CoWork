# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import atexit
import asyncio
from collections.abc import Awaitable
from collections.abc import Generator
from contextlib import contextmanager
from threading import Lock
from typing import Any, TypeVar

import httpx
from sqlalchemy.orm import Session

from rag.config import Settings, get_settings
from rag.db.config import DatabaseProvider, create_database
from rag.service.arxiv.pdf_downloader import PDFDownloader
from rag.service.elasticsearch import ElasticsearchClient, create_elasticsearch_client
from rag.service.embedding import EmbeddingProvider, create_embedding
from rag.service.storage import StorageProvider, create_s3_storage

_database_lock = Lock()
_worker_database: DatabaseProvider | None = None
_worker_database_url: str | None = None

_storage_lock = Lock()
_worker_storage: StorageProvider | None = None
_worker_storage_key: str | None = None

_elasticsearch_lock = Lock()
_worker_elasticsearch_client: ElasticsearchClient | None = None
_worker_elasticsearch_key: str | None = None

_embedding_lock = Lock()
_worker_embedding_provider: EmbeddingProvider | None = None
_worker_embedding_key: str | None = None

_pdf_downloader_lock = Lock()
_worker_pdf_downloader: PDFDownloader | None = None
_worker_pdf_downloader_key: str | None = None

_event_loop_lock = Lock()
_worker_event_loop: asyncio.AbstractEventLoop | None = None

T = TypeVar("T")


def worker_async_run(awaitable: Awaitable[T]) -> T:
    """
    Run an async function to completion inside the worker's event loop

    Args:
        awaitable: the given async function to be executed by worker

    Returns:
        The same result and type that awaited async function returns
    """
    global _worker_event_loop

    with _event_loop_lock:
        if _worker_event_loop is None or _worker_event_loop.is_closed():
            _worker_event_loop = asyncio.new_event_loop()

        return _worker_event_loop.run_until_complete(awaitable)


def shutdown_worker_event_loop() -> None:
    global _worker_event_loop

    with _event_loop_lock:
        if _worker_event_loop is not None and not _worker_event_loop.is_closed():
            _worker_event_loop.close()

        _worker_event_loop = None


def _settings_key(settings: Any) -> str:
    """
    Parse pydantic settings class to string for comparison
    """
    model_dump_json = getattr(settings, "model_dump_json", None)

    return str(model_dump_json()) if callable(model_dump_json) else repr(settings)


def get_worker_database(settings: Settings | None = None) -> DatabaseProvider:
    """Create or get existing database provider for all workers"""
    settings = settings or get_settings()
    database_url = settings.postgres_settings.db_url

    global _worker_database, _worker_database_url

    with _database_lock:
        if _worker_database is None or _worker_database_url != database_url:
            if _worker_database is not None:
                _worker_database.shutdown()

            _worker_database = create_database(settings)
            _worker_database.startup()
            _worker_database_url = database_url

        return _worker_database


def shutdown_worker_database() -> None:
    """Shutdown database provider when worker process exits"""
    global _worker_database, _worker_database_url

    with _database_lock:
        if _worker_database is not None:
            _worker_database.shutdown()

        _worker_database = None
        _worker_database_url = None


def get_worker_storage(settings: Settings | None = None) -> StorageProvider:
    """Create or get existing object storage provider for all workers"""
    settings = settings or get_settings()
    storage_key = _settings_key(settings.s3_settings)

    global _worker_storage, _worker_storage_key

    with _storage_lock:
        if _worker_storage is None or _worker_storage_key != storage_key:
            if _worker_storage is not None:
                _worker_storage.close()

            _worker_storage = create_s3_storage(settings)
            _worker_storage.ensure_bucket_exists()
            _worker_storage_key = storage_key

        return _worker_storage


def shutdown_worker_storage() -> None:
    """Shutdown object storage provider when worker process exits"""
    global _worker_storage, _worker_storage_key

    with _storage_lock:
        if _worker_storage is not None:
            _worker_storage.close()

        _worker_storage = None
        _worker_storage_key = None


def get_worker_elasticsearch_client(
    settings: Settings | None = None,
) -> ElasticsearchClient:
    """Create or get existing elasticsearch client for all workers"""
    settings = settings or get_settings()
    elasticsearch_key = _settings_key(settings.elasticsearch_settings)

    global _worker_elasticsearch_client, _worker_elasticsearch_key

    with _elasticsearch_lock:
        if (
            _worker_elasticsearch_client is None
            or _worker_elasticsearch_key != elasticsearch_key
        ):
            if _worker_elasticsearch_client is not None:
                _worker_elasticsearch_client.close()

            _worker_elasticsearch_client = create_elasticsearch_client(settings)
            _worker_elasticsearch_key = elasticsearch_key

        return _worker_elasticsearch_client


def shutdown_worker_elasticsearch_client() -> None:
    """Shutdown elasticsearch client when worker process exits"""
    global _worker_elasticsearch_client, _worker_elasticsearch_key

    with _elasticsearch_lock:
        if _worker_elasticsearch_client is not None:
            _worker_elasticsearch_client.close()

        _worker_elasticsearch_client = None
        _worker_elasticsearch_key = None


def get_worker_embedding_provider(
    settings: Settings | None = None,
) -> EmbeddingProvider:
    """Create or get embedding model provider for all workers"""
    settings = settings or get_settings()
    embedding_key = _settings_key(settings.embedding_settings)

    global _worker_embedding_provider, _worker_embedding_key

    with _embedding_lock:
        if _worker_embedding_provider is None:
            _worker_embedding_provider = create_embedding(settings)
            _worker_embedding_key = embedding_key

        if _worker_embedding_key != embedding_key:
            raise RuntimeError("Worker embedding settings changed; restart the worker")

        return _worker_embedding_provider


def shutdown_worker_embedding_provider() -> None:
    """Shutdown embedding model provider when worker process exits"""
    global _worker_embedding_provider, _worker_embedding_key

    with _embedding_lock:
        if _worker_embedding_provider is not None:
            worker_async_run(_worker_embedding_provider.close())

        _worker_embedding_provider = None
        _worker_embedding_key = None


def get_worker_pdf_downloader(settings: Settings | None = None) -> PDFDownloader:
    """Create or get pdf downloader client for all workers"""
    settings = settings or get_settings()
    pdf_downloader_key = _settings_key(settings.arxiv_settings)

    global _worker_pdf_downloader, _worker_pdf_downloader_key

    with _pdf_downloader_lock:
        if _worker_pdf_downloader is None:
            client = httpx.AsyncClient(
                timeout=settings.arxiv_settings.download_timeout_seconds,
            )
            _worker_pdf_downloader = PDFDownloader(
                settings.arxiv_settings,
                client=client,
            )
            _worker_pdf_downloader_key = pdf_downloader_key

        if _worker_pdf_downloader_key != pdf_downloader_key:
            raise RuntimeError("Worker arXiv settings changed; restart the worker")

        return _worker_pdf_downloader


def shutdown_worker_pdf_downloader() -> None:
    """Shutdown pdf downloader client  when worker process exits"""
    global _worker_pdf_downloader, _worker_pdf_downloader_key

    with _pdf_downloader_lock:
        if _worker_pdf_downloader is not None:
            worker_async_run(_worker_pdf_downloader.close())

        _worker_pdf_downloader = None
        _worker_pdf_downloader_key = None


def shutdown_all_instances() -> None:
    shutdown_worker_embedding_provider()
    shutdown_worker_pdf_downloader()
    shutdown_worker_elasticsearch_client()
    shutdown_worker_storage()
    shutdown_worker_database()
    shutdown_worker_event_loop()


atexit.register(shutdown_all_instances)


@contextmanager
def get_db_session(
    settings: Settings | None = None,
) -> Generator[Session, None, None]:
    """
    Get database provider session
    """
    database = get_worker_database(settings)

    with database.get_session() as session:
        yield session


@contextmanager
def get_db_storage_session(
    settings: Settings | None = None,
) -> Generator[tuple[Session, StorageProvider], None, None]:
    """
    Get both database and object storage provider session
    """
    settings = settings or get_settings()

    database = get_worker_database(settings)
    storage = get_worker_storage(settings)

    with database.get_session() as session:
        yield session, storage


@contextmanager
def get_pdf_download_session(
    settings: Settings | None = None,
) -> Generator[tuple[Session, StorageProvider, PDFDownloader], None, None]:
    """
    Get all necessary provider session for pdf download worker
    """
    settings = settings or get_settings()

    database = get_worker_database(settings)
    storage = get_worker_storage(settings)
    pdf_downloader = get_worker_pdf_downloader(settings)

    with database.get_session() as session:
        yield session, storage, pdf_downloader


@contextmanager
def get_indexing_session(
    settings: Settings | None = None,
) -> Generator[
    tuple[Session, EmbeddingProvider, ElasticsearchClient],
    None,
    None,
]:
    """
    Get all necessary provider session for paper indexing worker
    """
    settings = settings or get_settings()

    database = get_worker_database(settings)
    embedding_provider = get_worker_embedding_provider(settings)
    elasticsearch_client = get_worker_elasticsearch_client(settings)

    with database.get_session() as session:
        yield session, embedding_provider, elasticsearch_client
