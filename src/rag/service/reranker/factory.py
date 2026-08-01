# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import Settings, get_settings
from rag.service.reranker.interface import RerankerProvider

from rag.service.reranker.transformers import TransformersReranker


def create_reranker_provider(settings: Settings | None = None) -> RerankerProvider:
    settings = settings or get_settings()

    return TransformersReranker(settings.reranker_settings)
