# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.service.embedding.config import EmbeddingProvider
from rag.service.embedding.embedding_exceptions import (
    EmbeddingProviderError,
    EmbeddingServiceError,
    EmbeddingValidationError,
)


class QueryEmbeddingService:
    """
    `QueryEmbeddingService` turns a search query into a vector embedding,
    through `embed_query()` method.
    """

    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self.embedding_provider = embedding_provider

    @property
    def model_name(self) -> str:
        return self.embedding_provider.model_name

    @property
    def dimension(self) -> int:
        return self.embedding_provider.dimension

    async def embed_query(self, query: str) -> list[float]:
        """
        Returns:
            1D matrix (vector) with a scalar type of `float`

        Raises:
            EmbeddingValidationError:
                if input text to embed is empty or invalid
            EmbeddingProviderError:
                if embedding provider request fails
            EmbeddingResponseError:
                if embedding provider response is malformed or invalid
        """
        if not query.strip():
            raise EmbeddingValidationError("Cannot embed empty query")

        try:
            return await self.embedding_provider.embed_query(query)

        except EmbeddingServiceError:
            raise

        except Exception as error:
            raise EmbeddingProviderError("Failed to embed query") from error
