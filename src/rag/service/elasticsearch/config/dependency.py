# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import Request

from rag.service.elasticsearch.config.client import ElasticsearchClient


def get_elasticsearch_client(request: Request) -> ElasticsearchClient:
    """
    FastAPI dependency for object storage
    """
    elasticsearch_client: ElasticsearchClient | None = getattr(
        request.app.state, "elasticsearch_client", None
    )

    if elasticsearch_client is None:
        raise RuntimeError("Elasticsearch client is not initialized on app.state")

    return elasticsearch_client
