# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class DirectRagServiceError(Exception):
    """Service exception for direct RAG orchestration failures."""


class DirectRagRetryableError(DirectRagServiceError):
    """Base exception for direct RAG failures that may succeed on retry."""


class DirectRagNonRetryableError(DirectRagServiceError):
    """Base exception for direct RAG failures that should not be retried."""


class DirectRagValidationError(DirectRagNonRetryableError, ValueError):
    """Direct RAG input or orchestration configuration is invalid."""
