# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class CompactPaperResponse(BaseModel):
    paper_id: UUID
    arxiv_id: str
    title: str
    authors: list[str]
    categories: list[str]
    published_date: datetime


class PaperMetadataResponse(BaseModel):
    version: int | None
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str
    doi: str | None


class PaperArtifactsResponse(BaseModel):
    pdf_object_key: str | None
    parsed_json_object_key: str | None
    parser_name: str | None


class PaperStatusResponse(BaseModel):
    ingestion_status: str
    parser_status: str
    chunking_status: str
    indexing_status: str


class ChunkErrorResponse(BaseModel):
    stage: Literal["embedding", "indexing"]
    message: str
    count: int


class PaperErrorsResponse(BaseModel):
    pdf_download_error: str | None
    parser_error: str | None
    chunking_error: str | None
    indexing_error: str | None
    chunk_errors: list[ChunkErrorResponse]


class PaperTimestampsResponse(BaseModel):
    created_at: datetime
    updated_at: datetime


class FullPaperResponse(BaseModel):
    paper_id: UUID
    arxiv_id: str
    metadata: PaperMetadataResponse
    artifacts: PaperArtifactsResponse
    status: PaperStatusResponse
    errors: PaperErrorsResponse
    timestamps: PaperTimestampsResponse


class PaperListResponse(BaseModel):
    output: Literal["compact", "full"]
    status: Literal["failed"] | None = None
    count: int
    limit: int
    offset: int
    papers: list[CompactPaperResponse | FullPaperResponse]


class PaperDetailResponse(BaseModel):
    output: Literal["compact", "full"]
    paper: CompactPaperResponse | FullPaperResponse
