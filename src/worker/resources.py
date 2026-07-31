# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from rag.config import Settings, get_settings
from rag.db.config import DatabaseProvider, create_database
from rag.service.elasticsearch import ElasticsearchClient, create_elasticsearch_client
from rag.service.embedding import EmbeddingProvider, create_embedding
from rag.service.storage import StorageProvider, create_s3_storage


@contextmanager
def worker_db_session(
    settings: Settings | None = None,
) -> Generator[Session, None, None]:
    settings = settings or get_settings()

    database = create_database(settings)

    database.startup()

    try:
        with database.get_session() as session:
            yield session

    finally:
        database.shutdown()


@contextmanager
def worker_session(
    settings: Settings | None = None,
) -> Generator[tuple[Session, StorageProvider], None, None]:
    settings = settings or get_settings()

    database = create_database(settings)
    storage = create_s3_storage(settings)

    database.startup()

    try:
        storage.ensure_bucket_exists()

        with database.get_session() as session:
            yield session, storage

    finally:
        storage.close()
        database.shutdown()


@contextmanager
def indexing_resources(
    settings: Settings | None = None,
) -> Generator[
    tuple[Session, StorageProvider, EmbeddingProvider, ElasticsearchClient],
    None,
    None,
]:
    settings = settings or get_settings()

    database: DatabaseProvider = create_database(settings)
    storage = create_s3_storage(settings)
    embedding_provider = create_embedding(settings)
    elasticsearch_client = create_elasticsearch_client(settings)

    database.startup()

    try:
        storage.ensure_bucket_exists()

        with database.get_session() as session:
            yield session, storage, embedding_provider, elasticsearch_client

    finally:
        storage.close()
        elasticsearch_client.close()
        database.shutdown()
