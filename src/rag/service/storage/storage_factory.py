# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import Settings, get_settings
from rag.service.storage.storage_interface import StorageProvider
from rag.service.storage.s3_storage import S3Storage


def create_s3_storage(settings: Settings | None = None) -> StorageProvider:
    settings = settings or get_settings()

    return S3Storage(settings.s3_settings)
