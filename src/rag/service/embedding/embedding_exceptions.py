# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class EmbeddingServiceError(Exception):
    """Service exception for embedding service failures (service level exception)"""


class EmbeddingRetryableError(EmbeddingServiceError):
    """Base exception for failure that may succeed on retry (base level exception)"""


class EmbeddingNonRetryableError(EmbeddingServiceError):
    """Base exception for failure that should not be retried (base level exception)"""


class EmbeddingProviderError(EmbeddingRetryableError):
    """Embedding provider request failed (retry-able)"""


class EmbeddingPersistenceError(EmbeddingRetryableError):
    """Local embedding state persistence failed (retry-able)"""


class EmbeddingValidationError(EmbeddingNonRetryableError):
    """Embedding input is invalid (non retry-able)"""


class EmbeddingResponseError(EmbeddingNonRetryableError):
    """Embedding provider response is malformed or invalid (non retry-able)"""
