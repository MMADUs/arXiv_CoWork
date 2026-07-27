# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import Request

from rag.service.cache.interface import CacheProvider


def get_cache_provider(request: Request) -> CacheProvider:
    """
    FastAPI dependency for cache provider
    """
    cache_provider: CacheProvider | None = getattr(
        request.app.state, "cache_provider", None
    )

    if cache_provider is None:
        raise RuntimeError("cache_provider is not initialized on app.state")

    return cache_provider
