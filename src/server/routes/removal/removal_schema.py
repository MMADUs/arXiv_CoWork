# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class DeletePaperMetadataResponse(BaseModel):
    """
    Route response schema for deleting paper metadata and stored artifacts.
    """

    paper_id: UUID
    arxiv_id: str
    title: str
    deleted_metadata: bool
    deleted_pdf: bool
    deleted_parsed_json: bool
    status: Literal["metadata_deleted"]


class DeletePaperIndexResponse(BaseModel):
    """
    Route response schema for deleting paper chunks and search index documents.
    """

    paper_id: UUID
    arxiv_id: str
    title: str
    deleted_postgres_chunks: int
    deleted_elasticsearch_documents: int
    elasticsearch_index_exists: bool
    elasticsearch_version_conflicts: int
    elasticsearch_failures: list[Any]
    status: Literal["index_deleted"]
