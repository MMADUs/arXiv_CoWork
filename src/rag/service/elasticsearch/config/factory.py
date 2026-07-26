# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import Settings, get_settings
from rag.service.elasticsearch.config.client import ElasticsearchClient


def create_elasticsearch_client(settings: Settings) -> ElasticsearchClient:
    settings = settings or get_settings()

    return ElasticsearchClient(settings.elasticsearch_settings)
