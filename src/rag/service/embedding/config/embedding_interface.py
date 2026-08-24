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

        Returns:
            boolean flag if connection is ok and any successful message
        """

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """
        embed one search query

        Returns:
            1D matrix (vector) with a scalar type of `float`
        """

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        embed document chunks for indexing

        Returns:
            list of 1D matrix (vector) with a scalar type of `float`
        """

    @abstractmethod
    async def close(self) -> None:
        """
        close ollama http client connection
        """
