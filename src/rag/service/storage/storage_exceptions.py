# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class StorageServiceError(Exception):
    """Service exception for storage provider failures (service level exception)"""


class StorageRetryableError(StorageServiceError):
    """Base exception for failure that may succeed on retry (base level exception)"""


class StorageNonRetryableError(StorageServiceError):
    """Base exception for failure that should not be retried (base level exception)"""


class StorageBucketError(StorageRetryableError):
    """Storage bucket access or creation failed (retry-able)"""


class StorageUploadError(StorageRetryableError):
    """Storage object upload failed (retry-able)"""


class StorageDownloadError(StorageRetryableError):
    """Storage object download failed (retry-able)"""


class StorageDeleteError(StorageRetryableError):
    """Storage object deletion failed (retry-able)"""


class StorageObjectCheckError(StorageRetryableError):
    """Storage object existence check failed (retry-able)"""


class StorageLocalFileNotFoundError(StorageNonRetryableError):
    """Local file for storage upload does not exist (non retry-able)"""


class StorageJsonError(StorageNonRetryableError):
    """Storage JSON object serialization or parsing failed (non retry-able)"""
