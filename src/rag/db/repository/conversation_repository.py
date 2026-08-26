# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rag.db.model import (
    ConversationMessageModel,
    ConversationMessageRole,
    ConversationMessageStatus,
    ConversationRoomModel,
)


class ConversationRepository:
    """
    ConversationRoomRepository provides database access for conversation rooms
    and their messages.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_room(self, title: str | None = None) -> ConversationRoomModel:
        room = ConversationRoomModel(title=self._clean_title(title))
        self.session.add(room)
        self.session.flush()
        return room

    def get_room_by_id(self, room_id: UUID) -> ConversationRoomModel | None:
        statement = select(ConversationRoomModel).where(
            ConversationRoomModel.id == room_id
        )
        return self.session.scalar(statement)

    def list_rooms(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ConversationRoomModel], int]:
        base_statement = select(ConversationRoomModel)
        total_statement = select(func.count()).select_from(base_statement.subquery())
        page_statement = (
            base_statement.order_by(ConversationRoomModel.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )

        rooms = list(self.session.scalars(page_statement))
        total = self.session.scalar(total_statement) or 0

        return rooms, total

    def update_room_title(
        self,
        room: ConversationRoomModel,
        title: str | None,
    ) -> ConversationRoomModel:
        room.title = self._clean_title(title)
        room.updated_at = datetime.now(timezone.utc)
        return room

    def delete_room(self, room: ConversationRoomModel) -> None:
        self.session.delete(room)

    def add_message(
        self,
        room: ConversationRoomModel,
        role: ConversationMessageRole,
        content: str,
        status: ConversationMessageStatus = ConversationMessageStatus.COMPLETED,
        metadata: dict[str, object] | None = None,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> ConversationMessageModel:
        message = ConversationMessageModel(
            room_id=room.id,
            role=role.value,
            content=content,
            status=status.value,
            error=error,
            message_metadata=dict(metadata or {}),
            completed_at=completed_at,
        )
        room.updated_at = datetime.now(timezone.utc)
        self.session.add(message)
        self.session.flush()
        return message

    def get_message(self, message_id: UUID) -> ConversationMessageModel | None:
        statement = select(ConversationMessageModel).where(
            ConversationMessageModel.id == message_id
        )
        return self.session.scalar(statement)

    def get_room_message(
        self,
        room_id: UUID,
        message_id: UUID,
    ) -> ConversationMessageModel | None:
        statement = select(ConversationMessageModel).where(
            ConversationMessageModel.room_id == room_id,
            ConversationMessageModel.id == message_id,
        )
        return self.session.scalar(statement)

    def update_message_content(
        self,
        message: ConversationMessageModel,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> ConversationMessageModel:
        message.content = content
        message.updated_at = datetime.now(timezone.utc)

        if metadata is not None:
            message.message_metadata = dict(metadata)

        room = self.get_room_by_id(message.room_id)
        if room is not None:
            room.updated_at = datetime.now(timezone.utc)

        return message

    def update_message_state(
        self,
        message: ConversationMessageModel,
        content: str,
        status: ConversationMessageStatus,
        metadata: dict[str, object] | None = None,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> ConversationMessageModel:
        message.content = content
        message.status = status.value
        message.error = error
        message.completed_at = completed_at
        message.updated_at = datetime.now(timezone.utc)

        if metadata is not None:
            message.message_metadata = dict(metadata)

        room = self.get_room_by_id(message.room_id)
        if room is not None:
            room.updated_at = datetime.now(timezone.utc)

        return message

    def list_messages(
        self,
        room_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ConversationMessageModel], int]:
        base_statement = select(ConversationMessageModel).where(
            ConversationMessageModel.room_id == room_id
        )
        total_statement = select(func.count()).select_from(base_statement.subquery())
        page_statement = (
            base_statement.order_by(ConversationMessageModel.created_at.asc())
            .limit(limit)
            .offset(offset)
        )

        messages = list(self.session.scalars(page_statement))
        total = self.session.scalar(total_statement) or 0

        return messages, total

    def _clean_title(self, title: str | None) -> str | None:
        if title is None:
            return None

        cleaned = " ".join(title.split())
        return cleaned or None
