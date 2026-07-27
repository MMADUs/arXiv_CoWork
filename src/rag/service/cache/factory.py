# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import Settings, get_settings
from rag.service.cache.interface import CacheProvider

from rag.service.cache.redis import RedisCache


def create_cache_provider(settings: Settings | None = None) -> CacheProvider:
    settings = settings or get_settings()

    return RedisCache(settings=settings.redis_settings)
