# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any
from abc import ABC, abstractmethod
from pathlib import Path


class StorageProvider(ABC):
    """
    Any object storage providers must inherit the `StorageProvider` class,
    strictly made due to most service class are dependent to the storage method
    """

    @abstractmethod
    def ensure_bucket_exists(self) -> None:
        """
        inspect bucket if exist, otherwise create new bucket
        """

    # def check_connection(self) -> tuple[bool, str]:
    #     """
    #     check client connection and bucket existence
    #     """
    #     ...

    @abstractmethod
    def close(self) -> None:
        """
        close client connection from storage
        """

    @abstractmethod
    def upload_file(self, local_path: Path, object_key: str) -> None:
        """
        upload object to storage
        """

    @abstractmethod
    def download_file(self, local_path: Path, object_key: str) -> None:
        """
        download object from storage
        """

    # def delete_file(self, object_key: str) -> None:
    #     """
    #     delete object from storage
    #     """
    #     ...

    @abstractmethod
    def upload_json(self, data: dict[str, Any], object_key: str) -> None:
        """
        store dictionary as json files, commonly used to store parsed pdf
        """

    @abstractmethod
    def download_json(self, object_key: str) -> dict[str, Any]:
        """
        download json from storage and load it as dictionary
        """
