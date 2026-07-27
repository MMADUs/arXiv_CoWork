# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """
    Any embedding providers must inherit the `EmbeddingProvider` class,
    this keeps any module that are dependent consistent when switching provider
    """

    provider_name: str
    model_name: str
    dimension: int

    @abstractmethod
    async def check_connection(self) -> tuple[bool, str]:
        """
        check ollama connection and model existence
        """

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """
        embed one search query
        """

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        embed document chunks for indexing
        """

    @abstractmethod
    async def close(self) -> tuple[bool, str]:
        """
        close ollama http client connection
        """
