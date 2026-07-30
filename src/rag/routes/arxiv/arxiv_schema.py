# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from rag.schema import ArxivQueryParams


class ArxivIngestRequest(BaseModel):
    keywords: list[str] | None = Field(default=None)
    title: list[str] | None = Field(default=None)
    abstract: list[str] | None = Field(default=None)
    authors: list[str] | None = Field(default=None)
    categories: list[str] | None = Field(default=None)
    exclude_categories: list[str] | None = Field(default=None)
    ids: list[str] | None = Field(default=None)
    submitted_from: datetime | None = Field(default=None)
    submitted_to: datetime | None = Field(default=None)
    max_results: int = Field(default=10, ge=1, le=2000)
    start: int = Field(default=0, ge=0)
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = (
        "submittedDate"
    )
    sort_order: Literal["ascending", "descending"] = "descending"
    download_pdf: bool = False

    def to_arxiv_query_params(self) -> ArxivQueryParams:
        if not self.has_search_signal():
            raise ValueError("At least one search field or ids must be provided")

        submitted_to = self.submitted_to or datetime.now(timezone.utc)
        submitted_from = self.submitted_from or submitted_to - timedelta(days=365 * 5)

        return ArxivQueryParams(
            all_terms=self.keywords,
            title_terms=self.title,
            abstract_terms=self.abstract,
            authors=self.authors,
            categories=self.categories,
            exclude_categories=self.exclude_categories,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
            ids=self.ids,
            max_results=self.max_results,
            start=self.start,
            sort_by=self.sort_by,
            sort_order=self.sort_order,
        )

    def has_search_signal(self) -> bool:
        search_fields = [
            self.keywords,
            self.title,
            self.abstract,
            self.authors,
            self.categories,
            self.exclude_categories,
            self.ids,
        ]

        return any(self._has_non_empty_value(values) for values in search_fields)

    def _has_non_empty_value(self, values: list[str] | None) -> bool:
        if values is None:
            return False

        return any(value.strip() for value in values)


class PaperIngestionItem(BaseModel):
    paper_id: UUID
    arxiv_id: str | None
    title: str | None
    authors: list[str]
    categories: list[str]
    published_date: datetime | None
    ingestion_status: str | None
    pdf_object_key: str | None
    download_error: str | None = None


class ArxivIngestResponse(BaseModel):
    papers_fetched: int
    papers_stored: int
    download_pdf: bool
    pdfs_downloaded: int
    pdfs_failed: int
    papers: list[PaperIngestionItem]


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


class DownloadPapersRequest(BaseModel):
    paper_ids: list[UUID] = Field(..., min_length=1)


class DownloadPapersResponse(BaseModel):
    requested: int
    downloaded: int
    failed: int
    papers: list[PaperIngestionItem]
