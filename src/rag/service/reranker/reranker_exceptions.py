# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class RerankerServiceError(Exception):
    """Service exception for reranker service failures (service level exception)"""


class RerankerRetryableError(RerankerServiceError):
    """Base exception for failure that may succeed on retry (base level exception)"""


class RerankerNonRetryableError(RerankerServiceError):
    """Base exception for failure that should not be retried (base level exception)"""


class RerankerProviderError(RerankerRetryableError):
    """Reranker provider execution failed (retry-able)"""


class RerankerModelLoadError(RerankerRetryableError):
    """Reranker model or tokenizer could not be loaded (retry-able)"""


class RerankerValidationError(RerankerNonRetryableError):
    """Reranker input is invalid (non retry-able)"""


class RerankerResponseError(RerankerNonRetryableError):
    """Reranker provider response is malformed or invalid (non retry-able)"""
