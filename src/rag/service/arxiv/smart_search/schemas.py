# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from rag.schema import ArxivQueryParams


class ArxivQueryPlan(BaseModel):
    """
    Editable arXiv query parameters generated from a natural-language request.
    """

    all_terms: list[str] | None = None
    title_terms: list[str] | None = None
    abstract_terms: list[str] | None = None
    authors: list[str] | None = None
    categories: list[str] | None = None
    exclude_categories: list[str] | None = None
    submitted_from: datetime | None = None
    submitted_to: datetime | None = None
    max_results: int = Field(default=20, ge=1, le=100)
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = "submittedDate"
    sort_order: Literal["ascending", "descending"] = "descending"
    explanation: str = ""

    def to_query_params(self) -> ArxivQueryParams:
        return ArxivQueryParams(
            all_terms=self.all_terms,
            title_terms=self.title_terms,
            abstract_terms=self.abstract_terms,
            authors=self.authors,
            categories=self.categories,
            exclude_categories=self.exclude_categories,
            submitted_from=self.submitted_from,
            submitted_to=self.submitted_to,
            max_results=self.max_results,
            sort_by=self.sort_by,
            sort_order=self.sort_order,
        )


class SmartSearchKnowledge(BaseModel):
    title: str | None = Field(default=None)
    keywords: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value):
        if value is None:
            return None

        title = " ".join(str(value).split())
        return title or None

    @field_validator("keywords", "authors", mode="before")
    @classmethod
    def none_list_to_empty(cls, value):
        if value is None:
            return []

        return value

    @field_validator("keywords", "authors")
    @classmethod
    def normalize_list(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for item in value:
            text = " ".join(str(item).split())
            key = text.casefold()

            if not text or key in seen:
                continue

            cleaned.append(text)
            seen.add(key)

        return cleaned
