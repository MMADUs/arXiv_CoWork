# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.service.elasticsearch.config import (
    BulkIndexResult,
    DeleteChunksByPaperResult,
    DeleteIndexResult,
    ElasticsearchClient,
    ESRawJsonResponse,
    EnsureIndexResult,
    InsertedBulkItem,
    SearchHit,
    SearchResult,
    create_elasticsearch_client,
)
from rag.service.elasticsearch.es_exceptions import (
    ElasticsearchBulkIndexError,
    ElasticsearchDeleteError,
    ElasticsearchIndexError,
    ElasticsearchNonRetryableError,
    ElasticsearchPaperNotFoundError,
    ElasticsearchPersistenceError,
    ElasticsearchResponseError,
    ElasticsearchRetryableError,
    ElasticsearchSearchError,
    ElasticsearchServiceError,
)
from rag.service.elasticsearch.indexing import (
    ChunkIndexingService,
    ChunkIndexingResult,
    PaperReindexResult,
)
from rag.service.elasticsearch.searching import SearchingService, SearchingServiceResult

__all__ = [
    "ElasticsearchClient",
    "ESRawJsonResponse",
    "EnsureIndexResult",
    "DeleteIndexResult",
    "InsertedBulkItem",
    "BulkIndexResult",
    "DeleteChunksByPaperResult",
    "SearchHit",
    "SearchResult",
    "create_elasticsearch_client",
    "ChunkIndexingService",
    "ChunkIndexingResult",
    "PaperReindexResult",
    "SearchingService",
    "SearchingServiceResult",
    "ElasticsearchServiceError",
    "ElasticsearchRetryableError",
    "ElasticsearchNonRetryableError",
    "ElasticsearchIndexError",
    "ElasticsearchSearchError",
    "ElasticsearchBulkIndexError",
    "ElasticsearchDeleteError",
    "ElasticsearchPersistenceError",
    "ElasticsearchPaperNotFoundError",
    "ElasticsearchResponseError",
]
