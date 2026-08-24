# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class ElasticsearchServiceError(Exception):
    """Service exception for Elasticsearch service failures (service level exception)"""


class ElasticsearchRetryableError(ElasticsearchServiceError):
    """Base exception for failure that may succeed on retry (base level exception)"""


class ElasticsearchNonRetryableError(ElasticsearchServiceError):
    """Base exception for failure that should not be retried (base level exception)"""


class ElasticsearchIndexError(ElasticsearchRetryableError):
    """Elasticsearch index management operation failed (retry-able)"""


class ElasticsearchSearchError(ElasticsearchRetryableError):
    """Elasticsearch search operation failed (retry-able)"""


class ElasticsearchBulkIndexError(ElasticsearchRetryableError):
    """Elasticsearch bulk indexing operation failed (retry-able)"""


class ElasticsearchDeleteError(ElasticsearchRetryableError):
    """Elasticsearch delete operation failed (retry-able)"""


class ElasticsearchPersistenceError(ElasticsearchRetryableError):
    """Local Elasticsearch workflow persistence failed (retry-able)"""


class ElasticsearchPaperNotFoundError(ElasticsearchNonRetryableError):
    """Requested paper does not exist locally (non retry-able)"""


class ElasticsearchResponseError(ElasticsearchNonRetryableError):
    """Elasticsearch response is malformed or invalid (non retry-able)"""
