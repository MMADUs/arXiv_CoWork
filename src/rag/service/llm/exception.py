# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class LLMProviderError(Exception):
    """Base class for LLM provider failures."""


class LLMConnectionError(LLMProviderError):
    """Could not reach the LLM backend."""


class LLMTimeoutError(LLMProviderError):
    """The LLM backend took too long to respond."""


class LLMResponseError(LLMProviderError):
    """The LLM backend responded, but with an error status or malformed payload."""
