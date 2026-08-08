# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
import httpx

from rag import __version__
from rag.config import get_settings
from rag.db.config import create_database
from rag.service.arxiv import ArxivClient
from rag.service.elasticsearch.config.factory import create_elasticsearch_client
from rag.service.embedding.config.factory import create_embedding
from rag.service.llm.factory import create_llm_provider
from rag.service.storage import create_s3_storage

from server.routes.direct_ask import router as direct_ask_router
from server.routes.health import router as health_router
from server.routes.indexing import router as indexing_router
from server.routes.ingestion import router as ingest_router
from server.routes.papers import router as paper_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    app.state.settings = settings

    # init database
    database = create_database(settings)
    database.startup()
    app.state.database = database

    # init storage
    s3_storage = create_s3_storage(settings)
    s3_storage.ensure_bucket_exists()
    app.state.s3_storage = s3_storage

    # init arXiv metadata client
    arxiv_http_client = httpx.AsyncClient(
        timeout=settings.arxiv_settings.fetch_timeout_seconds,
    )
    arxiv_client = ArxivClient(
        settings.arxiv_settings,
        client=arxiv_http_client,
    )
    app.state.arxiv_client = arxiv_client

    # init direct RAG services
    elasticsearch_client = create_elasticsearch_client(settings)
    app.state.elasticsearch_client = elasticsearch_client

    embedding_provider = create_embedding(settings)
    app.state.embedding_provider = embedding_provider

    llm_provider = create_llm_provider(settings)
    app.state.llm_provider = llm_provider

    app.state.reranker_provider = None

    logger.info("Application startup completed")

    try:
        yield

    finally:
        # shutdown phase
        await llm_provider.close()
        await embedding_provider.close()
        elasticsearch_client.close()
        await arxiv_client.close()
        database.shutdown()
        s3_storage.close()

        logger.info("Application shutdown completed")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        summary=settings.app_summary,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.include_router(router=ingest_router, prefix=settings.api_prefix)
    app.include_router(router=paper_router, prefix=settings.api_prefix)
    app.include_router(router=indexing_router, prefix=settings.api_prefix)
    app.include_router(router=direct_ask_router, prefix=settings.api_prefix)
    app.include_router(router=health_router, prefix=settings.api_prefix)

    return app


app = create_app()
