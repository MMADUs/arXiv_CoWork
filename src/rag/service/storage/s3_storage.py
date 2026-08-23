# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import json
import logging
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from rag.config import S3Settings
from rag.service.storage.exceptions import (
    StorageBucketError,
    StorageDeleteError,
    StorageDownloadError,
    StorageJsonError,
    StorageLocalFileNotFoundError,
    StorageObjectCheckError,
    StorageUploadError,
)
from rag.service.storage.interface import StorageProvider

logger = logging.getLogger(__name__)


class S3Storage(StorageProvider):
    """
    S3 Object Storage interface
    """

    def __init__(self, settings: S3Settings) -> None:
        self.settings = settings
        self.client = boto3.client(
            "s3",
            endpoint_url=self.settings.endpoint_url,
            aws_access_key_id=self.settings.access_key,
            aws_secret_access_key=self.settings.secret_key,
            region_name=self.settings.region_name,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=30,
                retries={
                    "max_attempts": 3,
                    "mode": "standard",
                },
            ),
        )
        logger.info("S3 client initialized")

    def check_connection(self) -> tuple[bool, str]:
        try:
            self.client.list_buckets()
            self.client.head_bucket(Bucket=self.settings.bucket_name)

        except (ClientError, BotoCoreError) as error:
            return False, str(error)

        return True, f"Connected to bucket: {self.settings.bucket_name}"

    def ensure_bucket_exists(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.settings.bucket_name)
            return

        except (ClientError, BotoCoreError) as error:
            status_code = (
                error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if isinstance(error, ClientError)
                else None
            )

            if status_code != 404:
                raise StorageBucketError(
                    f"Failed to access S3 bucket: {self.settings.bucket_name}"
                ) from error

        try:
            self.client.create_bucket(Bucket=self.settings.bucket_name)

        except (ClientError, BotoCoreError) as error:
            logger.exception(
                "Failed to create S3 bucket: bucket_name=%s",
                self.settings.bucket_name,
            )
            raise StorageBucketError(
                f"Failed to create S3 bucket: {self.settings.bucket_name}"
            ) from error

    def close(self) -> None:
        self.client.close()
        logger.info("S3 client connection closed")

    def upload_file(self, local_path: Path, object_key: str) -> None:
        try:
            if not local_path.exists():
                raise StorageLocalFileNotFoundError(
                    f"Upload file does not exist: {local_path}"
                )

            self.ensure_bucket_exists()

            self.client.upload_file(
                Filename=str(local_path),
                Bucket=self.settings.bucket_name,
                Key=object_key,
            )

        except StorageLocalFileNotFoundError:
            raise

        except (ClientError, BotoCoreError, OSError) as error:
            logger.exception(
                "Failed to upload file object: key=%s local_path=%s",
                object_key,
                local_path,
            )
            raise StorageUploadError(
                f"Failed to upload file object with key: {object_key} from {local_path}"
            ) from error

    def download_file(self, local_path: Path, object_key: str) -> None:
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)

            self.client.download_file(
                Filename=str(local_path),
                Bucket=self.settings.bucket_name,
                Key=object_key,
            )

        except (ClientError, BotoCoreError, OSError) as error:
            logger.exception(
                "Failed to download file object: key=%s local_path=%s",
                object_key,
                local_path,
            )
            raise StorageDownloadError(
                f"Failed to download file object with key: {object_key} to {local_path}"
            ) from error

    def delete_file(self, object_key: str) -> None:
        try:
            self.client.delete_object(
                Bucket=self.settings.bucket_name,
                Key=object_key,
            )

        except (ClientError, BotoCoreError) as error:
            logger.exception(
                "Failed to delete file object: key=%s",
                object_key,
            )
            raise StorageDeleteError(
                f"Failed to delete file object with key: {object_key}"
            ) from error

    def upload_json(self, data: dict[str, Any], object_key: str) -> None:
        try:
            self.ensure_bucket_exists()

            self.client.put_object(
                Bucket=self.settings.bucket_name,
                Key=object_key,
                Body=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
                ContentType="application/json",
            )

        except (TypeError, ValueError) as error:
            logger.exception(
                "Failed to serialize JSON object: key=%s",
                object_key,
            )
            raise StorageJsonError(
                f"Failed to serialize JSON object with key: {object_key}"
            ) from error

        except (ClientError, BotoCoreError) as error:
            logger.exception(
                "Failed to upload JSON object: key=%s",
                object_key,
            )
            raise StorageUploadError(
                f"Failed to upload JSON object with key: {object_key}"
            ) from error

    def download_json(self, object_key: str) -> dict[str, Any]:
        try:
            response = self.client.get_object(
                Bucket=self.settings.bucket_name,
                Key=object_key,
            )

            body = response["Body"].read().decode("utf-8")
            return json.loads(body)

        except (UnicodeDecodeError, JSONDecodeError) as error:
            logger.exception(
                "Failed to parse JSON object: key=%s",
                object_key,
            )
            raise StorageJsonError(
                f"Failed to parse JSON object with key: {object_key}"
            ) from error

        except (ClientError, BotoCoreError) as error:
            logger.exception(
                "Failed to download JSON object: key=%s",
                object_key,
            )
            raise StorageDownloadError(
                f"Failed to download JSON object with key: {object_key}"
            ) from error

    def is_object_exist(self, object_key: str) -> tuple[bool, dict[str, Any]]:
        try:
            response = self.client.head_object(
                Bucket=self.settings.bucket_name,
                Key=object_key,
            )

        except ClientError as error:
            status_code = error.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )

            if status_code == 404:
                return False, {}

            raise StorageObjectCheckError(
                f"Failed to check object existence with key: {object_key}"
            ) from error

        except BotoCoreError as error:
            raise StorageObjectCheckError(
                f"Failed to check object existence with key: {object_key}"
            ) from error

        metadata = {
            "content_type": response.get("ContentType"),
            "size_bytes": response.get("ContentLength"),
        }

        return True, metadata
