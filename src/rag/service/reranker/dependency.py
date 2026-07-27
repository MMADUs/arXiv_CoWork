# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import Request

from rag.service.reranker.interface import RerankerProvider


def get_reranker_provider(request: Request) -> RerankerProvider:
    """
    FastAPI dependency for reranker provider
    """
    reranker_provider: RerankerProvider | None = getattr(
        request.app.state, "reranker_provider", None
    )

    if reranker_provider is None:
        raise RuntimeError("reranker_provider is not initialized on app.state")

    return reranker_provider
