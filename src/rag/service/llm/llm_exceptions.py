# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class LLMServiceError(Exception):
    """Service exception for LLM service failures (service level exception)"""


class LLMRetryableError(LLMServiceError):
    """Base exception for failure that may succeed on retry (base level exception)"""


class LLMNonRetryableError(LLMServiceError):
    """Base exception for failure that should not be retried (base level exception)"""


class LLMProviderError(LLMRetryableError):
    """LLM provider request failed (retry-able)"""


class LLMConnectionError(LLMProviderError):
    """Could not reach the LLM backend (retry-able)"""


class LLMTimeoutError(LLMProviderError):
    """The LLM backend took too long to respond (retry-able)"""


class LLMValidationError(LLMNonRetryableError):
    """LLM input is invalid (non retry-able)"""


class LLMResponseError(LLMNonRetryableError):
    """The LLM backend responded with an invalid status or malformed payload (non retry-able)"""
