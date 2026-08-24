# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class ParserServiceError(Exception):
    """Service exception for parser service failures (service level exception)"""


class ParserRetryableError(ParserServiceError):
    """Base exception for failure that may succeed on retry (base level exception)"""


class ParserNonRetryableError(ParserServiceError):
    """Base exception for failure that should not be retried (base level exception)"""


class ParserExecutionError(ParserRetryableError):
    """PDF parser execution failed (retry-able)"""


class ParserStorageError(ParserRetryableError):
    """Parser storage operation failed (retry-able)"""


class ParserPersistenceError(ParserRetryableError):
    """Local paper parsing state persistence failed (retry-able)"""


class ParserPaperNotFoundError(ParserNonRetryableError):
    """Requested paper does not exist locally (non retry-able)"""


class ParserPdfNotStoredError(ParserNonRetryableError):
    """Requested paper has no stored PDF object key (non retry-able)"""


class ParserPdfValidationError(ParserNonRetryableError):
    """PDF file failed parser validation (non retry-able)"""
