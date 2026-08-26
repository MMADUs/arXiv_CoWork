# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateConversationRoomRequest(BaseModel):
    title: str | None = Field(default=None, max_length=256)


class UpdateConversationRoomRequest(BaseModel):
    title: str | None = Field(default=None, max_length=256)


class ConversationRoomResponse(BaseModel):
    room_id: UUID
    title: str | None
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
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class ConversationRoomDetailResponse(BaseModel):
    room: ConversationRoomResponse
    message_count: int
    message_total: int
    message_page: int
    message_page_size: int
    message_pages: int
    message_offset: int
    messages: list[ConversationMessageResponse]
