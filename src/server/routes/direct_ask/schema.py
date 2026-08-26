# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


RetrievalMode = Literal["bm25", "vector", "hybrid"]


class DirectAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    retrieval_mode: RetrievalMode = "hybrid"
    top_k: int = Field(default=8, ge=1, le=50)
    candidate_pool_size: int = Field(default=50, ge=1, le=500)
    use_reranker: bool = False
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


class DirectAskGuardrailResponse(BaseModel):
    decision: Literal["allow", "block"]
    risk_level: Literal["low", "medium", "high"]
    categories: list[str]
    reason: str | None
    safe_query: str | None
    response: str | None
    raw_response: dict[str, Any]


class DirectAskCitationResponse(BaseModel):
    source_number: int
    chunk_id: str
    paper_id: str
    arxiv_id: str
    title: str
    section_title: str | None
    pdf_url: str
    chunk_index: int
    score: float | None
    highlights: list[str]


class DirectAskSourceResponse(BaseModel):
    paper_source_number: int
    paper_id: str
    arxiv_id: str
    title: str
    authors: list[str]
    categories: list[str]
    published_date: str
    pdf_url: str
    pdf_storage_key: str | None
    citation_numbers: list[int]


class DirectAskUsageResponse(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_eval_duration_ms: float
    eval_duration_ms: float
    load_duration_ms: float
    latency_ms: float


class DirectAskMetadataResponse(BaseModel):
    retrieval_mode: RetrievalMode
    use_reranker: bool
    total_hits: int
    answer_model: str | None
    answer_usage: DirectAskUsageResponse | None
    reranker_model: str | None = None
    reranker_latency_ms: float | None = None


class DirectAskResponse(BaseModel):
    answer: str
    blocked: bool
    guardrail: DirectAskGuardrailResponse
    citations: list[DirectAskCitationResponse]
    sources: list[DirectAskSourceResponse]
    metadata: DirectAskMetadataResponse
