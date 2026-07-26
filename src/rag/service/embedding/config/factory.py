# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import Settings, get_settings
from rag.service.embedding.config.interface import EmbeddingProvider
from rag.service.embedding.config.ollama import OllamaEmbedding


def create_embedding(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()

    return OllamaEmbedding(settings=settings.embedding_settings)
