# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import Request

from rag.service.storage.interface import StorageProvider


def get_s3_storage(request: Request) -> StorageProvider:
    """
    FastAPI dependency for object storage
    """
    storage: StorageProvider | None = getattr(request.app.state, "s3_storage", None)

    if storage is None:
        raise RuntimeError("S3 storage is not initialized on app.state")

    return storage
