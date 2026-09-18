# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from rag.schema import ArxivPaperMetadata, ArxivQueryParams


class PaperIngestionRequest(BaseModel):
    """
    Router request schema for arxiv paper ingestion payload
    """

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
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = "submittedDate"
    sort_order: Literal["ascending", "descending"] = "descending"
    download_pdf: bool = False

    def to_arxiv_query_params(self) -> ArxivQueryParams:
        """
        Parse request payload into `ArxivQueryParams`
        """
        return _to_arxiv_query_params(
            keywords=self.keywords,
            title=self.title,
            abstract=self.abstract,
            authors=self.authors,
            categories=self.categories,
            exclude_categories=self.exclude_categories,
            ids=self.ids,
            submitted_from=self.submitted_from,
            submitted_to=self.submitted_to,
            max_results=self.max_results,
            start=self.start,
            sort_by=self.sort_by,
            sort_order=self.sort_order,
        )

    def has_search_signal(self) -> bool:
        """
        Check for a valid searchable field, at least one of them should exist

        This includes: keywords, title, abstract, authros, categories and arxiv ids
        """
        search_fields = [
            self.keywords,
            self.title,
            self.abstract,
            self.authors,
            self.categories,
            self.ids,
        ]

        return any(_has_non_empty_value(values) for values in search_fields)

    def _has_non_empty_value(self, values: list[str] | None) -> bool:
        return _has_non_empty_value(values)


class PaperIngestionItem(BaseModel):
    """
    Ingested paper item metadata, used as response item from bulk process
    """

    paper_id: UUID
    arxiv_id: str | None
    title: str | None
    authors: list[str]
    categories: list[str]
    published_date: datetime | None
    pdf_download_task_id: str | None = None
    pdf_download_status: str | None = None


class ArxivSearchRequest(BaseModel):
    """
    Search arXiv without writing results to the local database.
    """

    keywords: list[str] | None = Field(default=None)
    title: list[str] | None = Field(default=None)
    abstract: list[str] | None = Field(default=None)
    authors: list[str] | None = Field(default=None)
    categories: list[str] | None = Field(default=None)
    exclude_categories: list[str] | None = Field(default=None)
    ids: list[str] | None = Field(default=None)
    submitted_from: datetime | None = Field(default=None)
    submitted_to: datetime | None = Field(default=None)
    max_results: int = Field(default=20, ge=1, le=100)
    start: int = Field(default=0, ge=0)
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = "submittedDate"
    sort_order: Literal["ascending", "descending"] = "descending"

    def to_arxiv_query_params(self) -> ArxivQueryParams:
        return _to_arxiv_query_params(
            keywords=self.keywords,
            title=self.title,
            abstract=self.abstract,
            authors=self.authors,
            categories=self.categories,
            exclude_categories=self.exclude_categories,
            ids=self.ids,
            submitted_from=self.submitted_from,
            submitted_to=self.submitted_to,
            max_results=self.max_results,
            start=self.start,
            sort_by=self.sort_by,
            sort_order=self.sort_order,
        )


class ArxivSearchPaperItem(ArxivPaperMetadata):
    """
    arXiv search result annotated with local library membership.
    """

    already_exists: bool = False
    existing_paper_id: UUID | None = None


class ArxivSearchResponse(BaseModel):
    """
    Route response schema for arXiv search preview results.
    """

    count: int
    papers: list[ArxivSearchPaperItem]


class ArxivQueryPlanRequest(BaseModel):
    """
    Request schema for planning arXiv query params from natural language.
    """

    prompt: str = Field(..., min_length=1, max_length=2000)


class ArxivQueryPlanResponse(BaseModel):
    """
    Route response schema for LLM-generated arXiv query params.
    """

    keywords: list[str] | None = None
    title: list[str] | None = None
    abstract: list[str] | None = None
    authors: list[str] | None = None
    categories: list[str] | None = None
    exclude_categories: list[str] | None = None
    submitted_from: datetime | None = None
    submitted_to: datetime | None = None
    max_results: int
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"]
    sort_order: Literal["ascending", "descending"]
    explanation: str


class SelectedPapersIngestionRequest(BaseModel):
    """
    Request schema for saving selected arXiv metadata and queueing PDF downloads.
    """

    papers: list[ArxivPaperMetadata] = Field(..., min_length=1, max_length=200)


class SelectedPapersIngestionResponse(BaseModel):
    """
    Route response schema for selected paper ingestion result.
    """

    requested: int
    created: int
    updated: int
    pdf_downloads_queued: int
    pdf_downloads_skipped: int
    papers: list[PaperIngestionItem]


class ArxivIngestResponse(BaseModel):
    """
    Route response schema for arxiv paper ingestion result
    """

    papers_fetched: int
    papers_stored: int
    download_pdf: bool
    pdf_downloads_queued: int
    pdf_downloads_skipped: int
    papers: list[PaperIngestionItem]


class DownloadPaperRequest(BaseModel):
    """
    Router request schema for pdf paper download payload
    """

    force_download: bool = False


class DownloadPendingPapersRequest(BaseModel):
    """
    Router request schema for download all pending pdf paper download payload
    """

    limit: int = Field(default=50, ge=1, le=500)
    include_failed: bool = False


class DownloadPaperItem(BaseModel):
    """
    Downloaded paper item metadata, used as response item from bulk process
    """

    paper_id: UUID
    arxiv_id: str
    title: str
    task_id: str | None
    pdf_download_status: str


class DownloadPaperResponse(BaseModel):
    """
    Route response schema for pdf paper download result
    """

    requested: int
    queued: int
    skipped: int
    papers: list[DownloadPaperItem]


def _to_arxiv_query_params(
    *,
    keywords: list[str] | None,
    title: list[str] | None,
    abstract: list[str] | None,
    authors: list[str] | None,
    categories: list[str] | None,
    exclude_categories: list[str] | None,
    ids: list[str] | None,
    submitted_from: datetime | None,
    submitted_to: datetime | None,
    max_results: int,
    start: int,
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"],
    sort_order: Literal["ascending", "descending"],
) -> ArxivQueryParams:
    if not any(
        _has_non_empty_value(values)
        for values in [keywords, title, abstract, authors, categories, ids]
    ):
        raise ValueError("At least one search field or ids must be provided")

    return ArxivQueryParams(
        all_terms=keywords,
        title_terms=title,
        abstract_terms=abstract,
        authors=authors,
        categories=categories,
        exclude_categories=exclude_categories,
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        ids=ids,
        max_results=max_results,
        start=start,
        sort_by=sort_by,
        sort_order=sort_order,
    )


def _has_non_empty_value(values: list[str] | None) -> bool:
    if values is None:
        return False

    return any(value.strip() for value in values)
