# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import asdict
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from rag.db.model import ConversationMessageStatus
from rag.service.conversation import (
    ConversationNotFoundError,
    ConversationRoomService,
    ConversationTitleStreamParser,
    ConversationValidationError,
)
from rag.service.llm import (
    LLMGenerationSettings,
    LLMServiceError,
)
from rag.service.llm.llm_interface import LLMProvider
from server.dependencies import get_db_session, get_llm_provider
from server.routes.conversation.conversation_event import (
    ConversationEventType,
    _message_payload,
    _room_payload,
    _sse_event,
)
from server.routes.conversation.conversation_schema import (
    ConversationMessageResponse,
    ConversationRoomDetailResponse,
    ConversationRoomListResponse,
    ConversationRoomResponse,
    CreateConversationMessageRequest,
    CreateConversationRoomRequest,
    UpdateConversationMessageRequest,
    UpdateConversationRoomRequest,
)

router = APIRouter(prefix="/conversation-rooms", tags=["conversation-room"])


@router.post(
    "",
    response_model=ConversationRoomResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_room_route(
    request: CreateConversationRoomRequest,
    session: Session = Depends(get_db_session),
) -> ConversationRoomResponse:
    service = ConversationRoomService(session)
    room = service.create_conversation_room(title=request.title)
    return ConversationRoomResponse.model_validate(room, from_attributes=True)


@router.get("", response_model=ConversationRoomListResponse)
def list_conversation_rooms_route(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> ConversationRoomListResponse:
    service = ConversationRoomService(session)

    offset = (page - 1) * page_size
    result = service.list_conversation_rooms(limit=page_size, offset=offset)

    return ConversationRoomListResponse(
        count=len(result.rooms),
        total=result.total,
        page=page,
        page_size=page_size,
        pages=ceil(result.total / page_size) if result.total else 0,
        offset=offset,
        rooms=[
            ConversationRoomResponse.model_validate(room, from_attributes=True)
            for room in result.rooms
        ],
    )


@router.get("/{room_id}", response_model=ConversationRoomDetailResponse)
def get_conversation_route(
    room_id: UUID,
    message_page: int = Query(default=1, ge=1),
    message_page_size: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> ConversationRoomDetailResponse:
    service = ConversationRoomService(session)

    message_offset = (message_page - 1) * message_page_size

    try:
        detail = service.get_conversation_room_and_messages(
            room_id=room_id,
            message_limit=message_page_size,
            message_offset=message_offset,
        )

    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return ConversationRoomDetailResponse(
        room=ConversationRoomResponse.model_validate(
            detail.room,
            from_attributes=True,
        ),
        message_count=len(detail.messages),
        message_total=detail.total_messages,
        message_page=message_page,
        message_page_size=message_page_size,
        message_pages=(
            ceil(detail.total_messages / message_page_size)
            if detail.total_messages
            else 0
        ),
        message_offset=message_offset,
        messages=[
            ConversationMessageResponse.model_validate(
                message,
                from_attributes=True,
            )
            for message in detail.messages
        ],
    )


@router.patch("/{room_id}", response_model=ConversationRoomResponse)
def update_room_route(
    room_id: UUID,
    request: UpdateConversationRoomRequest,
    session: Session = Depends(get_db_session),
) -> ConversationRoomResponse:
    service = ConversationRoomService(session)

    try:
        room = service.update_conversation_room_title(
            room_id=room_id, title=request.title
        )

    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return ConversationRoomResponse.model_validate(room, from_attributes=True)


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room_route(
    room_id: UUID,
    session: Session = Depends(get_db_session),
) -> None:
    service = ConversationRoomService(session)

    try:
        service.delete_conversation_room(room_id)

    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.post(
    "/{room_id}/messages",
    status_code=status.HTTP_200_OK,
)
async def send_message_route(
    room_id: UUID,
    request: CreateConversationMessageRequest,
    connection: Request,
    session: Session = Depends(get_db_session),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> StreamingResponse:
    service = ConversationRoomService(session)

    try:
        room = service.get_conversation_room(room_id)

    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    async def event_stream() -> AsyncGenerator[str, None]:
        assistant_message = None
        title_parser = ConversationTitleStreamParser(enabled=room.title is None)
        full_text = ""

        try:
            # 1. create user message
            user_message = service.create_user_message(
                room_id=room_id,
                content=request.content,
                metadata=request.metadata,
            )
            yield _sse_event(
                ConversationEventType.CONVERSATION_MESSAGE_CREATED,
                _message_payload(user_message),
            )

            # 2. initialize assitant message
            assistant_message = service.create_assistant_placeholder(room_id=room_id)
            yield _sse_event(
                ConversationEventType.ASSISTANT_MESSAGE_CREATED,
                _message_payload(assistant_message),
            )

            # 3. prepare prompt + generation settings
            prompt = service.build_conversation_prompt(
                room_id=room_id,
                include_title_instruction=room.title is None,
            )
            generation_settings = LLMGenerationSettings(
                reasoning=False if room.title is None else None,
            )

            # 4. start generating + thinking message
            yield _sse_event(
                ConversationEventType.ASSISTANT_STATUS,
                {"text": "Thinking..."},
            )

            async for chunk in llm_provider.stream(
                prompt=prompt,
                settings=generation_settings,
            ):
                if await connection.is_disconnected():
                    raise asyncio.CancelledError

                generated_title, answer_chunk = title_parser.parse_response(chunk)

                if generated_title is not None:
                    current_room = service.get_conversation_room(room_id)

                    if generated_title and current_room.title is None:
                        updated_room = service.update_conversation_room_title(
                            room_id=room_id,
                            new_title=generated_title,
                        )
                        yield _sse_event(
                            ConversationEventType.CONVERSATION_ROOM_UPDATED,
                            _room_payload(updated_room),
                        )

                if answer_chunk:
                    full_text += answer_chunk
                    yield _sse_event(
                        ConversationEventType.ASSISTANT_FRAGMENT,
                        {"text": answer_chunk},
                    )

            remaining_text = title_parser.finish()

            if remaining_text:
                full_text += remaining_text
                yield _sse_event(
                    ConversationEventType.ASSISTANT_FRAGMENT,
                    {"text": remaining_text},
                )

            if await connection.is_disconnected():
                raise asyncio.CancelledError

            answer = full_text.strip()

            usage = getattr(llm_provider, "last_stream_usage", None)

            metadata: dict[str, object] = {
                "model": llm_provider.model_name,
                "provider": llm_provider.provider_name,
                "usage": None if usage is None else asdict(usage),
                "output_limited": (
                    usage is not None
                    and usage.completion_tokens >= generation_settings.max_tokens
                ),
            }

            assistant_message = service.update_assistant_generation(
                room_id=room_id,
                message_id=assistant_message.message_id,
                content=answer or "I could not generate a response.",
                status=ConversationMessageStatus.COMPLETED,
                metadata=metadata,
            )
            yield _sse_event(
                ConversationEventType.ASSISTANT_COMPLETED,
                _message_payload(assistant_message),
            )

        except asyncio.CancelledError:
            if assistant_message is not None:
                service.update_assistant_generation(
                    room_id=room_id,
                    message_id=assistant_message.message_id,
                    content=full_text,
                    status=ConversationMessageStatus.INTERRUPTED,
                )
            raise

        except ConversationValidationError as error:
            if assistant_message is not None:
                service.update_assistant_generation(
                    room_id=room_id,
                    message_id=assistant_message.message_id,
                    content=full_text,
                    status=ConversationMessageStatus.FAILED,
                    error=str(error),
                )
            yield _sse_event(
                ConversationEventType.ASSISTANT_ERROR,
                {"message": str(error)},
            )

        except LLMServiceError as error:
            if assistant_message is not None:
                service.update_assistant_generation(
                    room_id=room_id,
                    message_id=assistant_message.message_id,
                    content=full_text,
                    status=ConversationMessageStatus.FAILED,
                    error=str(error),
                )
            yield _sse_event(
                ConversationEventType.ASSISTANT_ERROR,
                {"message": f"LLM response failed: {error}"},
            )

        except Exception as error:
            if assistant_message is not None:
                service.update_assistant_generation(
                    room_id=room_id,
                    message_id=assistant_message.message_id,
                    content=full_text,
                    status=ConversationMessageStatus.FAILED,
                    error=str(error),
                )
            yield _sse_event(
                ConversationEventType.ASSISTANT_ERROR,
                {"message": f"Conversation stream failed: {error}"},
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch(
    "/{room_id}/messages/{message_id}",
    response_model=ConversationMessageResponse,
)
def update_message_route(
    room_id: UUID,
    message_id: UUID,
    request: UpdateConversationMessageRequest,
    session: Session = Depends(get_db_session),
) -> ConversationMessageResponse:
    service = ConversationRoomService(session)

    try:
        message = service.update_conversation_message(
            room_id=room_id,
            message_id=message_id,
            content=request.content,
            metadata=request.metadata,
        )

    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except ConversationValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    return ConversationMessageResponse.model_validate(
        message,
        from_attributes=True,
    )
