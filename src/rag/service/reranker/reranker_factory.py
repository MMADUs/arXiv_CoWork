# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import Settings, get_settings
from rag.service.reranker.reranker_interface import RerankerProvider

from rag.service.reranker.hf_transformers import HFTransformersReranker


def create_reranker_provider(settings: Settings | None = None) -> RerankerProvider:
    settings = settings or get_settings()

    return HFTransformersReranker(settings.reranker_settings)
