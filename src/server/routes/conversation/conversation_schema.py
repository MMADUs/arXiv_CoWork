# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

RetrievalMode = Literal["bm25", "vector", "hybrid"]


class CreateConversationRoomRequest(BaseModel):
    title: str | None = Field(default=None, max_length=256)


class UpdateConversationRoomRequest(BaseModel):
    title: str | None = Field(default=None, max_length=256)


class ConversationRoomResponse(BaseModel):
    room_id: UUID
    title: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ConversationRoomListResponse(BaseModel):
    count: int
    total: int
    page: int
    page_size: int
    pages: int
    offset: int
    rooms: list[ConversationRoomResponse]


class CreateConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
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


class UpdateConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    metadata: dict[str, Any] | None = None


class ConversationMessageResponse(BaseModel):
    message_id: UUID
    room_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    status: Literal["completed", "generating", "interrupted", "failed"]
    error: str | None
    metadata: dict[str, Any]
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationSourcePaperResponse(BaseModel):
    paper_source_number: int | None = None
    paper_id: UUID
    arxiv_id: str | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    published_date: str | None = None
    pdf_url: str | None = None
    citation_numbers: list[int] = Field(default_factory=list)


class ConversationSourceChunkResponse(BaseModel):
    source_number: int | None = None
    chunk_id: UUID
    paper_id: UUID
    section_title: str | None = None
    chunk_index: int
    score: float | None = None
    highlights: list[str] = Field(default_factory=list)
    text: str
    word_count: int
    start_word: int
    end_word: int
    start_char: int
    end_char: int


class ConversationSourceChunksResponse(BaseModel):
    paper: ConversationSourcePaperResponse
    chunks: list[ConversationSourceChunkResponse]


class ConversationRoomDetailResponse(BaseModel):
    room: ConversationRoomResponse
    message_count: int
    message_total: int
    message_page: int
    message_page_size: int
    message_pages: int
    message_offset: int
    messages: list[ConversationMessageResponse]
