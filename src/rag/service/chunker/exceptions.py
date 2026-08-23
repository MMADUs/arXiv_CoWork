# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class ChunkerServiceError(Exception):
    """Service exception for chunker service failures (service level exception)"""


class ChunkerRetryableError(ChunkerServiceError):
    """Base exception for failure that may succeed on retry (base level exception)"""


class ChunkerNonRetryableError(ChunkerServiceError):
    """Base exception for failure that should not be retried (base level exception)"""


class ChunkerExecutionError(ChunkerRetryableError):
    """Text chunking execution failed (retry-able)"""


class ChunkerStorageError(ChunkerRetryableError):
    """Chunker storage operation failed (retry-able)"""


class ChunkerPersistenceError(ChunkerRetryableError):
    """Local paper chunking state persistence failed (retry-able)"""


class ChunkerPaperNotFoundError(ChunkerNonRetryableError):
    """Requested paper does not exist locally (non retry-able)"""


class ChunkerParsedDocumentNotFoundError(ChunkerNonRetryableError):
    """Requested paper has no parsed document object key (non retry-able)"""


class ChunkerParsedDocumentValidationError(ChunkerNonRetryableError):
    """Parsed document artifact is malformed or invalid (non retry-able)"""


class ChunkerConfigurationError(ChunkerNonRetryableError):
    """Chunker configuration is invalid (non retry-able)"""
