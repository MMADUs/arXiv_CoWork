# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class CacheProvider(ABC):
    @abstractmethod
    def get_cached_response(self, request: BaseModel) -> dict[str, Any] | None:
        """
        get response from prior request cache
        """

    @abstractmethod
    def set_cache_response(self, request: BaseModel, response: BaseModel) -> None:
        """
        insert the final upstream response to cache
        """

    @abstractmethod
    def close(self) -> None:
        """
        close cache client connection provider
        """
