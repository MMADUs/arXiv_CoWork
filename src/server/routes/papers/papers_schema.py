# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class MetadataResponseGroup(BaseModel):
    """
    Paper metadata related response group in full paper format
    """

    version: int | None
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str
    doi: str | None


class ArtifactsResponseGroup(BaseModel):
    """
    Paper artifacts related response group in full paper format
    """

    pdf_object_key: str | None
    parsed_json_object_key: str | None
    parser_name: str | None


class StatusResponseGroup(BaseModel):
    """
    Paper statuses related response group in full paper format
    """

    ingestion_status: str
    parser_status: str
    chunking_status: str
    indexing_status: str


class ChunkErrorItem(BaseModel):
    """
    Each chunk item error from a paper error
    """

    stage: Literal["embedding", "indexing"]
    message: str
    count: int


class ErrorsResponseGroup(BaseModel):
    """
    Paper error related response group in full paper format
    """

    pdf_download_error: str | None
    parser_error: str | None
    chunking_error: str | None
    indexing_error: str | None
    chunk_errors: list[ChunkErrorItem]


class TimestampsResponseGroup(BaseModel):
    """
    Timestamp related response group in full paper format
    """

    created_at: datetime
    updated_at: datetime


class FullPaperFormat(BaseModel):
    """
    Full paper item response, this includes metadata, statuses, errors, and timestamps
    """

    paper_id: UUID
    arxiv_id: str
    metadata: MetadataResponseGroup
    artifacts: ArtifactsResponseGroup
    status: StatusResponseGroup
    errors: ErrorsResponseGroup
    timestamps: TimestampsResponseGroup


class CompactPaperFormat(BaseModel):
    """
    Compacted paper item response, mostly just the widely seen paper metadata itself
    """

    paper_id: UUID
    arxiv_id: str
    title: str
    authors: list[str]
    categories: list[str]
    published_date: datetime


class PaperListResponse(BaseModel):
    """
    Route response schema for list of paper result
    """

    output: Literal["compact", "full"]
    status: Literal["failed"] | None = None
    count: int
    total: int
    page: int
    page_size: int
    pages: int
    offset: int
    papers: list[FullPaperFormat | CompactPaperFormat]


class PaperDetailResponse(BaseModel):
    """
    Route response schema for get paper by id result
    """

    output: Literal["compact", "full"]
    paper: FullPaperFormat | CompactPaperFormat
