# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.service.arxiv.arxiv_client import ArxivClient
from rag.service.arxiv.arxiv_ingestion_service import (
    ArxivIngestionService,
    ArxivIngestionResult,
    IngestedPaperResult,
)
from rag.service.arxiv.exceptions import (
    ArxivInvalidDownloadedPdfError,
    ArxivInvalidPdfUrlError,
    ArxivMalformedEntryError,
    ArxivMetadataFetchError,
    ArxivMetadataParseError,
    ArxivNonRetryableError,
    ArxivPaperNotFoundError,
    ArxivPdfDownloadError,
    ArxivPersistenceError,
    ArxivRetryableError,
    ArxivServiceError,
    ArxivStorageError,
)

from rag.service.arxiv.paper_download_service import PaperDownloadService

from rag.service.arxiv.utils import make_arxiv_id_safe

__all__ = [
    "ArxivClient",
    "ArxivIngestionService",
    "ArxivIngestionResult",
    "IngestedPaperResult",
    "ArxivInvalidDownloadedPdfError",
    "ArxivInvalidPdfUrlError",
    "ArxivMalformedEntryError",
    "ArxivMetadataFetchError",
    "ArxivMetadataParseError",
    "ArxivNonRetryableError",
    "ArxivPaperNotFoundError",
    "ArxivPdfDownloadError",
    "ArxivPersistenceError",
    "ArxivRetryableError",
    "ArxivServiceError",
    "ArxivStorageError",
    "PaperDownloadService",
    "make_arxiv_id_safe",
]
