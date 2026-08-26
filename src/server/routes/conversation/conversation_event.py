# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import json
from enum import StrEnum


class ConversationEventType(StrEnum):
    """
    Conversation event type string enum class.

    Available enum members:
    - CONVERSATION_MESSAGE_CREATED
    - CONVERSATION_ROOM_UPDATED
    - ASSISTANT_MESSAGE_CREATED
    - ASSISTANT_STATUS
    - ASSISTANT_FRAGMENT
    - ASSISTANT_COMPLETED
    - ASSISTANT_ERROR
    """

    CONVERSATION_MESSAGE_CREATED = "conversation.message.created"
    CONVERSATION_ROOM_UPDATED = "conversation.room.updated"
    ASSISTANT_MESSAGE_CREATED = "assistant.message.created"
    ASSISTANT_STATUS = "assistant.status"
    ASSISTANT_FRAGMENT = "assistant.fragment"
    ASSISTANT_COMPLETED = "assistant.completed"
    ASSISTANT_ERROR = "assistant.error"


def _sse_event(event: ConversationEventType, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _message_payload(message) -> dict[str, object]:
    return {
        "message_id": str(message.message_id),
        "room_id": str(message.room_id),
        "role": message.role,
        "content": message.content,
        "status": message.status,
        "error": message.error,
        "metadata": message.metadata,
        "completed_at": message.completed_at,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
    }


def _room_payload(room) -> dict[str, object]:
    return {
        "room_id": str(room.room_id),
        "title": room.title,
        "created_at": room.created_at,
        "updated_at": room.updated_at,
    }
