# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

RetrievalMode = Literal["bm25", "vector", "hybrid"]


class AgenticAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    thread_id: str | None = Field(default=None, max_length=256)
    retrieval_mode: RetrievalMode | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    candidate_pool_size: int | None = Field(default=None, ge=1, le=500)
    use_reranker: bool | None = None
    num_candidates: int | None = Field(default=None, ge=1, le=10_000)
    categories: list[str] | None = None
    paper_id: UUID | None = None
    published_from: date | None = None
    published_to: date | None = None
    latest_first: bool = False
    min_score: float | None = None
    track_total_hits: bool = True
    include_highlights: bool = False
    fuzziness: str | None = Field(default=None, max_length=32)


class AgenticAskResponse(BaseModel):
    thread_id: str
    answer: str
    blocked: bool
    guardrail: dict[str, Any] | None
    citations: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    metadata: dict[str, Any]
