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


class FullPaperResponse(BaseModel):
    paper_id: UUID
    arxiv_id: str
    version: int | None
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str
    doi: str | None
    pdf_object_key: str | None
    parsed_json_object_key: str | None
    parser_name: str | None
    parser_error: str | None
    ingestion_status: str
    parser_status: str
    indexing_status: str
    created_at: datetime
    updated_at: datetime


class PaperListResponse(BaseModel):
    output: Literal["compact", "full"]
    count: int
    limit: int
    offset: int
    papers: list[CompactPaperResponse | FullPaperResponse]


class PaperDetailResponse(BaseModel):
    output: Literal["compact", "full"]
    paper: CompactPaperResponse | FullPaperResponse
