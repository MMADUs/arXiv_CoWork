# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rag.db.model import (
    ConversationMessageModel,
    ConversationMessageRole,
    ConversationMessageStatus,
)
from rag.db.repository import ConversationRepository
from rag.service.conversation.conversation_exceptions import (
    ConversationNotFoundError,
    ConversationValidationError,
)


@dataclass(frozen=True, slots=True)
class ConversationRoom:
    room_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    message_id: UUID
    room_id: UUID
    role: str
    content: str
    status: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConversationRoomPage:
    rooms: list[ConversationRoom]
    total: int


@dataclass(frozen=True, slots=True)
class ConversationMessagePage:
    messages: list[ConversationMessage]
    total: int


@dataclass(frozen=True, slots=True)
class ConversationRoomDetail:
    room: ConversationRoom
    messages: list[ConversationMessage]
    total_messages: int


class ConversationRoomService:
    """
    Product-level service for durable conversation rooms and messages.

    This intentionally does not call the LLM yet. It is the persistence layer
    the direct or agentic chat flow can plug into later.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ConversationRepository(session)

    def create_conversation_room(self, title: str | None = None) -> ConversationRoom:
        """
        Create new conversation room with the given room title
        """
        room = self.repository.create_room(title=title)
        self.session.commit()
        self.session.refresh(room)
        return self._room_from_model(room)

    def list_conversation_rooms(
        self, limit: int = 50, offset: int = 0
    ) -> ConversationRoomPage:
        """
        List conversation rooms with limit and offset for pagination support
        """
        rooms, total = self.repository.list_rooms(limit=limit, offset=offset)
        return ConversationRoomPage(
            rooms=[self._room_from_model(room) for room in rooms],
            total=total,
        )

    def get_conversation_room(self, room_id: UUID) -> ConversationRoom:
        """
        Get conversation room
        """
        room = self.repository.get_room_by_id(room_id)

        if room is None:
            raise ConversationNotFoundError(f"Conversation room not found: {room_id}")

        return self._room_from_model(room)

    def get_conversation_room_and_messages(
        self,
        room_id: UUID,
        message_limit: int = 100,
        message_offset: int = 0,
    ) -> ConversationRoomDetail:
        """
        Get conversation room along with its message in the room
        """
        room = self.repository.get_room_by_id(room_id)

        if room is None:
            raise ConversationNotFoundError(f"Conversation room not found: {room_id}")

        messages, total = self.repository.list_messages(
            room_id=room_id,
            limit=message_limit,
            offset=message_offset,
        )

        return ConversationRoomDetail(
            room=self._room_from_model(room),
            messages=[self._message_from_model(message) for message in messages],
            total_messages=total,
        )

    def update_conversation_room_title(
        self,
        room_id: UUID,
        new_title: str | None,
    ) -> ConversationRoom:
        """
        Update only the room title for a custom room name
        """
        room = self.repository.get_room_by_id(room_id)

        if room is None:
            raise ConversationNotFoundError(f"Conversation room not found: {room_id}")

        self.repository.update_room_title(room=room, title=new_title)
        self.session.commit()
        self.session.refresh(room)
        return self._room_from_model(room)

    def delete_conversation_room(self, room_id: UUID) -> None:
        """
        Delete conversation room, this will also delete the message inside the room
        """
        room = self.repository.get_room_by_id(room_id)

        if room is None:
            raise ConversationNotFoundError(f"Conversation room not found: {room_id}")

        self.repository.delete_room(room)
        self.session.commit()

    def create_user_message(
        self,
        room_id: UUID,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> ConversationMessage:
        """
        Create message from user prompt
        """
        return self._add_message(
            room_id=room_id,
            role=ConversationMessageRole.USER,
            content=content,
            status=ConversationMessageStatus.COMPLETED,
            metadata=metadata,
        )

    def create_assistant_placeholder(self, room_id: UUID) -> ConversationMessage:
        """
        Since LLM generation are streamed, create a placeholder message
        with `ConversationMessageStatus.GENERATING` status, later after streamed response
        is finished, update assistant placeholder with generated response
        """
        return self._add_message(
            room_id=room_id,
            role=ConversationMessageRole.ASSISTANT,
            content="",
            status=ConversationMessageStatus.GENERATING,
            metadata={},
            allow_empty=True,
        )

    # NOTE: the temporary prompt builder for ordinary conversation with the LLM,
    #       later when integrating with agentic rag, this should be gone
    def build_conversation_prompt(
        self,
        room_id: UUID,
        history_limit: int = 20,
        include_title_instruction: bool = False,
    ) -> str:
        """
        Build conversation prompt from conversation message (chat) history,
        this also includes prompt for generating response to automatically asign topic
        name for conversation room title.

        Args:
            room_id:
                ID of the conversation room whose history should be included
            history_limit:
                maximum number of past conversation message to be included into the prompt
            include_title_instruction:
                include the automatic title generation instruction into the prompt

        Raises:
            ConversationValidationError:
                If ``history_limit`` is less than one.
        """
        if history_limit < 1:
            raise ConversationValidationError("history_limit must be greater than 0")

        first_page = self._list_messages(
            room_id=room_id,
            limit=1,
            offset=0,
        )
        offset = max(
            first_page.total - history_limit, 0
        )  # get the last N `history_limit` message
        page = self._list_messages(
            room_id=room_id,
            limit=history_limit,
            offset=offset,
        )

        lines = [
            "You are a helpful research assistant.",
            "Answer the latest user message using the conversation context.",
            (
                "Do not reveal hidden reasoning. If useful, briefly summarize "
                "what you checked."
            ),
        ]

        if include_title_instruction:
            lines.extend(
                [
                    "This is the first answer in a new conversation.",
                    "Begin with exactly one hidden title tag in this format:",
                    (
                        "<conversation_title>Concise 3 to 7 word title"
                        "</conversation_title>"
                    ),
                    (
                        "Summarize the user's task or topic; do not copy long "
                        "input verbatim."
                    ),
                    "After the closing tag, write the answer normally.",
                ]
            )

        lines.extend(["", "# Conversation"])

        for message in page.messages:
            role_name = {
                ConversationMessageRole.USER.value: "User",
                ConversationMessageRole.ASSISTANT.value: "Assistant",
                ConversationMessageRole.SYSTEM.value: "System",
            }.get(message.role, message.role.title())

            lines.append(f"{role_name}: {message.content}")

        lines.extend(["", "Assistant:"])

        return "\n".join(lines)

    def update_assistant_generation(
        self,
        room_id: UUID,
        message_id: UUID,
        content: str,
        status: ConversationMessageStatus,
        metadata: dict[str, object] | None = None,
        error: str | None = None,
    ) -> ConversationMessage:
        """
        Update the placeholder made by `create_assistant_placeholder()` with
        the full response after stream generation is finished.
        """
        message = self.repository.get_room_message(
            room_id=room_id,
            message_id=message_id,
        )

        if message is None:
            raise ConversationNotFoundError(
                f"Conversation message not found: {message_id}"
            )

        if message.role != ConversationMessageRole.ASSISTANT.value:
            raise ConversationValidationError(
                "only assistant messages can be updated as generation output"
            )

        completed_at = (
            datetime.now(timezone.utc)
            if status == ConversationMessageStatus.COMPLETED
            else None
        )

        self.repository.update_message_state(
            message=message,
            content=content,
            status=status,
            metadata=metadata,
            error=error,
            completed_at=completed_at,
        )
        self.session.commit()
        self.session.refresh(message)

        return self._message_from_model(message)

    def update_conversation_message(
        self,
        room_id: UUID,
        message_id: UUID,
        new_content: str,
        metadata: dict[str, object] | None = None,
    ) -> ConversationMessage:
        """
        Update conversation message in a conversation room
        """
        if self.repository.get_room_by_id(room_id) is None:
            raise ConversationNotFoundError(f"Conversation room not found: {room_id}")

        message = self.repository.get_room_message(
            room_id=room_id,
            message_id=message_id,
        )

        if message is None:
            raise ConversationNotFoundError(
                f"Conversation message not found: {message_id}"
            )

        cleaned_content = self._clean_content(new_content)

        self.repository.update_message_content(
            message=message,
            content=cleaned_content,
            metadata=metadata,
        )
        self.session.commit()
        self.session.refresh(message)

        return self._message_from_model(message)

    def _add_message(
        self,
        room_id: UUID,
        role: ConversationMessageRole,
        content: str,
        status: ConversationMessageStatus = ConversationMessageStatus.COMPLETED,
        metadata: dict[str, object] | None = None,
        allow_empty: bool = False,
    ) -> ConversationMessage:
        """
        Add message to database, the message can be identified by role (eg: user or assistant)
        """
        room = self.repository.get_room_by_id(room_id)

        if room is None:
            raise ConversationNotFoundError(f"Conversation room not found: {room_id}")

        cleaned_content = self._clean_content(content, allow_empty=allow_empty)
        completed_at = (
            datetime.now(timezone.utc)
            if status == ConversationMessageStatus.COMPLETED
            else None
        )

        message = self.repository.add_message(
            room=room,
            role=role,
            content=cleaned_content,
            status=status,
            metadata=metadata,
            completed_at=completed_at,
        )
        self.session.commit()
        self.session.refresh(message)

        return self._message_from_model(message)

    def _list_messages(
        self,
        room_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> ConversationMessagePage:
        if self.repository.get_room_by_id(room_id) is None:
            raise ConversationNotFoundError(f"Conversation room not found: {room_id}")

        messages, total = self.repository.list_messages(
            room_id=room_id,
            limit=limit,
            offset=offset,
        )
        return ConversationMessagePage(
            messages=[self._message_from_model(message) for message in messages],
            total=total,
        )

    def _clean_content(self, content: str, allow_empty: bool = False) -> str:
        cleaned = content.strip()

        if not cleaned and not allow_empty:
            raise ConversationValidationError("message content must not be empty")

        return cleaned

    def _room_from_model(self, room) -> ConversationRoom:
        return ConversationRoom(
            room_id=room.id,
            title=room.title,
            created_at=room.created_at,
            updated_at=room.updated_at,
        )

    def _message_from_model(
        self,
        message: ConversationMessageModel,
    ) -> ConversationMessage:
        return ConversationMessage(
            message_id=message.id,
            room_id=message.room_id,
            role=message.role,
            content=message.content,
            status=message.status,
            error=message.error,
            metadata=dict(message.message_metadata or {}),
            completed_at=message.completed_at,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )
