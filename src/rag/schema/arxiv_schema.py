# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ArxivQueryParams(BaseModel):
    """
    arxiv api search query parameters
    reference field from official docs: https://info.arxiv.org/help/api/user-manual.html
    """

    all_terms: list[str] | None = Field(
        default=None,
        description="Terms searched across all arXiv searchable fields.",
    )
    title_terms: list[str] | None = Field(
        default=None,
        description="Terms searched only in paper titles.",
    )
    abstract_terms: list[str] | None = Field(
        default=None,
        description="Terms searched only in abstracts.",
    )
    authors: list[str] | None = Field(
        default=None,
        description="Author names searched with arXiv au: field.",
    )
    categories: list[str] | None = Field(
        default=None,
        description="arXiv categories that must be present, e.g. cs.AI.",
    )
    exclude_categories: list[str] | None = Field(
        default=None,
        description="arXiv categories that must not be present.",
    )
    submitted_from: datetime | None = Field(
        default=None,
        description="Lower bound for submittedDate. Converted to UTC YYYYMMDDHHMM.",
    )
    submitted_to: datetime | None = Field(
        default=None,
        description="Upper bound for submittedDate. Converted to UTC YYYYMMDDHHMM.",
    )
    ids: list[str] | None = Field(
        default=None,
        description="Specific arXiv IDs. Sent as id_list.",
    )

    max_results: int = Field(
        default=30,
        ge=0,
        le=2000,  # upper bound (should be emptied or set proper number)
        description="Number of results to fetch in one request.",
    )
    start: int = Field(
        default=0,
        ge=0,
        description="Zero-based pagination offset.",
    )
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = Field(
        default="submittedDate",
        description="arXiv sort field.",
    )
    sort_order: Literal["ascending", "descending"] = Field(
        default="descending",
        description="arXiv sort direction.",
    )

    @field_validator(
        "all_terms",
        "title_terms",
        "abstract_terms",
        "authors",
        "categories",
        "exclude_categories",
        "ids",
        mode="before",
    )
    @classmethod
    def empty_list_to_none(cls, value):
        if value == []:
            return None
        return value

    @field_validator(
        "all_terms",
        "title_terms",
        "abstract_terms",
        "authors",
        "categories",
        "exclude_categories",
        "ids",
    )
    @classmethod
    def strip_list_values(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        cleaned = [item.strip() for item in value if item and item.strip()]

        return cleaned or None

    @model_validator(mode="after")
    def validate_date_range(self) -> "ArxivQueryParams":
        if (
            self.submitted_from is not None
            and self.submitted_to is not None
            and self.submitted_from > self.submitted_to
        ):
            raise ValueError("submitted_from must be before submitted_to")

        return self

    @model_validator(mode="after")
    def validate_query_exists(self) -> "ArxivQueryParams":
        has_search_query = any(
            [
                self.all_terms,
                self.title_terms,
                self.abstract_terms,
                self.authors,
                self.categories,
                self.exclude_categories,
                self.submitted_from,
                self.submitted_to,
            ]
        )

        if not has_search_query and not self.ids:
            raise ValueError("At least one search filter or ids must be provided")

        return self


class ArxivPaperMetadata(BaseModel):
    """
    arxiv paper metadata fetched by `ArxivClient`
    """

    arxiv_id: str = Field(..., description="arxiv paper id e.g: `2401.12345`")
    version: int | None = Field(default=None, description="paper version")
    title: str = Field(..., description="paper title")
    authors: list[str] = Field(..., description="paper authors")
    abstract: str = Field(..., description="paper abstract")
    categories: list[str] = Field(..., description="paper categories")
    published_date: datetime = Field(..., description="paper published date")
    pdf_url: str | None = Field(
        default=None,
        description="arxiv paper pdf origin url e.g: `https://arxiv.org/pdf/1706.03762`",
    )
    doi: str | None = Field(default=None, description="paper DOI")


