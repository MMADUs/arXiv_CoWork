# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import Request

from rag.service.embedding.config.interface import EmbeddingProvider


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    """
    FastAPI dependency for embedding provider
    """
    embedding_provider: EmbeddingProvider | None = getattr(request.app.state, "embedding_provider", None)

    if embedding_provider is None:
        raise RuntimeError("Embedding provider is not initialized on app.state")

    return embedding_provider