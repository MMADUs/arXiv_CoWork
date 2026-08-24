# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import httpx

from rag.config import OllamaEmbeddingSettings
from rag.service.embedding.config.embedding_interface import EmbeddingProvider
from rag.service.embedding.embedding_exceptions import (
    EmbeddingProviderError,
    EmbeddingResponseError,
    EmbeddingValidationError,
)


class OllamaEmbedding(EmbeddingProvider):
    """
    Ollama embedding provider

    Uses Ollama's `/api/embed` endpoint, which accepts either a single
    string or a list of strings via `input` and always returns a list of
    embeddings.

    This replaces the legacy `/api/embeddings` endpoint, which
    only accepted one prompt per request and has been superseded.
    """

    provider_name: str = "ollama"

    def __init__(self, settings: OllamaEmbeddingSettings) -> None:
        # satisfy interface
        self.model_name = settings.model_name
        self.dimension = settings.dimension

        self.base_url = settings.base_url.rstrip("/")
        self.batch_size = settings.batch_size
        self.timeout_seconds = settings.timeout_seconds

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        )

    async def check_connection(self):
        try:
            response = await self.client.get(url="/api/tags")

            # check for error status
            response.raise_for_status()
            data = response.json()

        except Exception as error:
            return False, f"Could not connect to ollama: {error}"

        models = data.get("models", [])

        models_name = {
            model_info.get("name")
            for model_info in models
            if isinstance(model_info, dict)
        }

        if self.model_name not in models_name:
            return (
                False,
                f"Connected to Ollama but the model {self.model_name} is not available",
            )

        return True, f"Connected to Ollama along with the model {self.model_name}"

    async def embed_query(self, text: str) -> list[float]:
        """
        embed query to vector embedding, embed 1 batch at a time

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
        if not text.strip():
            raise EmbeddingValidationError("Cannot embed empty text")

        embeddings = await self._embed_batch(
            texts=[text],
        )
        return embeddings[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        embed chunk documents to vector embedding, embed N batch at a time

        Returns:
            list of 1D matrix (vector) with a scalar type of `float`

        Raises:
            EmbeddingValidationError:
                if input text to embed is empty or invalid
            EmbeddingProviderError:
                if embedding provider request fails
            EmbeddingResponseError:
                if embedding provider response is malformed or invalid
        """
        if not texts:
            return []

        for text in texts:
            if not text.strip():
                raise EmbeddingValidationError("Cannot embed empty text")

        embeddings: list[list[float]] = []

        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            embeddings.extend(
                await self._embed_batch(
                    texts=batch,
                )
            )

        return embeddings

    async def _embed_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        body = {
            "model": self.model_name,
            "input": texts,
        }

        try:
            response = await self.client.post(
                url="/api/embed",
                json=body,
            )

            # check for error status
            response.raise_for_status()

            data = response.json()

        except httpx.HTTPError as error:
            raise EmbeddingProviderError(
                f"Ollama embedding request failed: {error}"
            ) from error

        except ValueError as error:
            raise EmbeddingResponseError(
                "Ollama embedding response is not valid JSON"
            ) from error

        embeddings = data.get("embeddings")

        if not isinstance(embeddings, list):
            raise EmbeddingResponseError(
                "Ollama embedding response is not a list of vectors"
            )

        if len(embeddings) != len(texts):
            raise EmbeddingResponseError(
                f"Expected {len(texts)} embeddings, got {len(embeddings)} instead"
            )

        result: list[list[float]] = []

        for embedding in embeddings:
            if not isinstance(embedding, list):
                raise EmbeddingResponseError(
                    "Ollama embedding response contains a non-vector item"
                )

            if len(embedding) != self.dimension:
                raise EmbeddingResponseError(
                    "Expected "
                    f"{self.dimension} embedding dimension, "
                    f"got {len(embedding)} instead"
                )

            try:
                result.append([float(v) for v in embedding])

            except (TypeError, ValueError) as error:
                raise EmbeddingResponseError(
                    "Ollama embedding response contains a non-numeric vector value"
                ) from error

        return result

    async def close(self) -> None:
        await self.client.aclose()
