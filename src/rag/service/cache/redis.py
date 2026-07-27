# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel
from redis import asyncio as redis_async

from rag.config import RedisSettings
from rag.service.cache.interface import CacheProvider

logger = logging.getLogger(__name__)


class RedisCache(CacheProvider):
    def __init__(self, settings: RedisSettings) -> None:
        self.redis_client = redis_async.from_url(
            url=settings.url,
            decode_response=True,
            socket_timeout=settings.timeout_seconds,
            socket_connect_timeout=settings.timeout_seconds,
        )
        self.key_prefix = settings.key_prefix
        self.cache_ttl_seconds = settings.cache_ttl_seconds

    async def get_cached_response(
        self,
        request: BaseModel,
    ) -> dict[str, Any] | None:
        cache_key = self._cache_key(request)

        try:
            payload = await self.redis_client.get(cache_key)

        except Exception:
            logger.warning("Answer cache read failed: key=%s", cache_key, exc_info=True)
            return None

        if payload is None:
            return None

        try:
            data = json.loads(payload)

        except json.JSONDecodeError:
            logger.warning("Answer cache payload is invalid JSON: key=%s", cache_key)
            return None

        return data if isinstance(data, dict) else None

    async def set_cache_response(
        self,
        request: BaseModel,
        response: BaseModel,
    ) -> None:
        cache_key = self._cache_key(request)

        try:
            await self.redis_client.set(
                cache_key,
                response.model_dump_json(),
                ex=self.cache_ttl_seconds,
            )

        except Exception:
            logger.warning(
                "Answer cache write failed: key=%s",
                cache_key,
                exc_info=True,
            )

    async def close(self) -> None:
        close = getattr(self.redis_client, "aclose", None)

        if close is not None:
            await close()
            return

        self.redis_client.close()

    def cache_key(self, request: BaseModel) -> str:
        return self._cache_key(request)

    def _cache_key(self, request: BaseModel) -> str:
        key_data = request.model_dump(mode="json")

        if isinstance(key_data.get("categories"), list):
            key_data["categories"] = sorted(key_data["categories"])

        key_string = json.dumps(key_data, sort_keys=True)

        key_hash = hashlib.sha256(key_string.encode("utf-8")).hexdigest()

        return f"{self.key_prefix}:answer_cache:{key_hash}"
