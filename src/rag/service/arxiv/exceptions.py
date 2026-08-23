# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class ArxivServiceError(Exception):
    """Service exception for arXiv service failures (service level exception)"""


class ArxivRetryableError(ArxivServiceError):
    """Base exception for failure that may succeed on retry (base level exception)"""


class ArxivNonRetryableError(ArxivServiceError):
    """Base exception for failure that should not be retried (base level exception)"""


class ArxivMetadataFetchError(ArxivRetryableError):
    """arXiv metadata API request failed (retry-able)"""


class ArxivPdfDownloadError(ArxivRetryableError):
    """arXiv PDF download failed (retry-able)"""


class ArxivStorageError(ArxivRetryableError):
    """Paper PDF storage operation failed (retry-able)"""


class ArxivPersistenceError(ArxivRetryableError):
    """Local paper metadata persistence failed (retry-able)"""


class ArxivMetadataParseError(ArxivNonRetryableError):
    """arXiv metadata response could not be parsed (non retry-able)"""


class ArxivMalformedEntryError(ArxivNonRetryableError):
    """A single arXiv metadata entry is malformed (non retry-able)"""


class ArxivPaperNotFoundError(ArxivNonRetryableError):
    """Requested paper does not exist locally (non retry-able)"""


class ArxivInvalidPdfUrlError(ArxivNonRetryableError):
    """Paper PDF URL is invalid (non retry-able)"""


class ArxivInvalidDownloadedPdfError(ArxivNonRetryableError):
    """Downloaded paper PDF is empty or invalid (non retry-able)"""
