# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.service.embedding.config import EmbeddingProvider


class QueryEmbeddingService:
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self.embedding_provider = embedding_provider

    @property
    def model_name(self) -> str:
        return self.embedding_provider.model_name

    @property
    def dimension(self) -> int:
        return self.embedding_provider.dimension

    async def embed_query(self, query: str) -> list[float]:
        return await self.embedding_provider.embed_query(query)
