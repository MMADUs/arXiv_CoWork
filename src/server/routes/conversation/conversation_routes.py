# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress
from math import ceil
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.model import ConversationMessageStatus
from rag.service.conversation import (
    ConversationMessage,
    ConversationNotFoundError,
    ConversationRoomService,
    ConversationValidationError,
)
from rag.service.elasticsearch.config.es_client import ElasticsearchClient
from rag.service.elasticsearch.searching import SearchingService
from rag.service.embedding.config.embedding_interface import EmbeddingProvider
from rag.service.llm import LLMServiceError
from rag.service.llm.llm_interface import LLMProvider
from rag.service.orchestration.core.agentic import (
    AgenticRAGOrchestrator,
    AgenticRAGRequest,
)
from rag.service.reranker.reranker_interface import RerankerProvider
from server.dependencies import (
    get_db_session,
    get_elasticsearch_client,
    get_embedding_provider,
    get_llm_provider,
    get_optional_reranker_provider,
)
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
            room_id=room_id, new_title=request.title
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
    elasticsearch_client: ElasticsearchClient = Depends(get_elasticsearch_client),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    reranker_provider: RerankerProvider | None = Depends(
        get_optional_reranker_provider
    ),
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
        agentic_task: asyncio.Task | None = None
        full_text = ""

        try:
            # 1. create user message
            user_message = service.create_user_message(
                room_id=room_id,
                content=request.content,
                metadata={},
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

            if room.title is None:
                updated_room = service.update_conversation_room_title(
                    room_id=room_id,
                    new_title=_derive_room_title(request.content),
                )
                yield _sse_event(
                    ConversationEventType.CONVERSATION_ROOM_UPDATED,
                    _room_payload(updated_room),
                )

            # 3. load compact recent history and run agentic RAG
            recent_context = _conversation_context_payload(
                [
                    message
                    for message in service.list_recent_messages(
                        room_id=room_id,
                        limit=8,
                    ).messages
                    if message.message_id != user_message.message_id
                ]
            )

            settings = get_settings()
            if not settings.agentic_rag_settings.enabled:
                raise LLMServiceError("Agentic RAG is disabled.")

            searching_service = SearchingService(
                elasticsearch_client=elasticsearch_client,
                embedding_provider=embedding_provider,
            )
            orchestrator = AgenticRAGOrchestrator(
                settings=settings.agentic_rag_settings,
                searching_service=searching_service,
                llm_provider=llm_provider,
                reranker_provider=reranker_provider,
            )

            status_queue: asyncio.Queue[str] = asyncio.Queue()

            async def emit_status(text: str) -> None:
                await status_queue.put(text)

            agentic_task = asyncio.create_task(
                orchestrator.answer(
                    AgenticRAGRequest(
                        question=request.content,
                        thread_id=str(room_id),
                        conversation_id=str(room_id),
                        current_message_id=str(user_message.message_id),
                        conversation_context=recent_context,
                        retrieval_mode=request.retrieval_mode,
                        top_k=request.top_k,
                        candidate_pool_size=request.candidate_pool_size,
                        use_reranker=request.use_reranker,
                        num_candidates=request.num_candidates,
                        categories=request.categories,
                        paper_id=(
                            str(request.paper_id)
                            if request.paper_id is not None
                            else None
                        ),
                        published_from=(
                            request.published_from.isoformat()
                            if request.published_from is not None
                            else None
                        ),
                        published_to=(
                            request.published_to.isoformat()
                            if request.published_to is not None
                            else None
                        ),
                        latest_first=request.latest_first,
                        min_score=request.min_score,
                        track_total_hits=request.track_total_hits,
                        include_highlights=request.include_highlights,
                        fuzziness=request.fuzziness,
                    ),
                    status_callback=emit_status,
                )
            )

            while not agentic_task.done():
                if await connection.is_disconnected():
                    agentic_task.cancel()
                    raise asyncio.CancelledError

                try:
                    status_text = await asyncio.wait_for(
                        status_queue.get(),
                        timeout=0.25,
                    )
                    yield _sse_event(
                        ConversationEventType.ASSISTANT_STATUS,
                        {"text": status_text},
                    )
                except asyncio.TimeoutError:
                    continue

            while not status_queue.empty():
                yield _sse_event(
                    ConversationEventType.ASSISTANT_STATUS,
                    {"text": status_queue.get_nowait()},
                )

            result = await agentic_task
            answer = result.answer.strip() or "I could not generate a response."
            full_text = answer

            if answer:
                yield _sse_event(
                    ConversationEventType.ASSISTANT_FRAGMENT,
                    {"text": answer},
                )

            if await connection.is_disconnected():
                raise asyncio.CancelledError

            result_metadata = result.metadata.to_dict()
            usage_metadata = _usage_metadata_fields(
                result_metadata.get("answer_usage")
            )
            metadata: dict[str, object] = {
                "thread_id": result.thread_id,
                "conversation_id": result_metadata.get("conversation_id"),
                "current_message_id": result_metadata.get("current_message_id"),
                "resolved_query": result_metadata.get("resolved_query"),
                "rewritten_query": result_metadata.get("rewritten_query"),
                "retrieval_used": result_metadata.get("retrieval_used", False),
                "evidence_grade": result_metadata.get("evidence_grade", {}),
                "provider": llm_provider.provider_name,
                "model": result.metadata.answer_model or llm_provider.model_name,
                **usage_metadata,
                "output_limited": False,
                "blocked": result.blocked,
                "citations": [citation.to_dict() for citation in result.citations],
                "sources": [source.to_dict() for source in result.sources],
                "errors": result_metadata.get("errors", []),
            }

            assistant_message = service.update_assistant_generation(
                room_id=room_id,
                message_id=assistant_message.message_id,
                content=answer,
                status=ConversationMessageStatus.COMPLETED,
                metadata=metadata,
            )
            yield _sse_event(
                ConversationEventType.ASSISTANT_COMPLETED,
                _message_payload(assistant_message),
            )

            updated_room = service.refresh_conversation_room_metadata(room_id)
            yield _sse_event(
                ConversationEventType.CONVERSATION_ROOM_UPDATED,
                _room_payload(updated_room),
            )

        except asyncio.CancelledError:
            if agentic_task is not None:
                agentic_task.cancel()
                with suppress(asyncio.CancelledError):
                    await agentic_task

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
            new_content=request.content,
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


def _conversation_context_payload(
    messages: list[ConversationMessage],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []

    for message in messages:
        metadata = message.metadata or {}
        payload.append(
            {
                "message_id": str(message.message_id),
                "role": message.role,
                "content": message.content,
                "citations": _compact_citations(metadata.get("citations", [])),
                "sources": _compact_sources(metadata.get("sources", [])),
                "resolved_query": metadata.get("resolved_query"),
                "retrieval_used": metadata.get("retrieval_used", False),
            }
        )

    return payload


def _compact_citations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    citations: list[dict[str, Any]] = []
    for citation in value:
        if not isinstance(citation, dict):
            continue

        citations.append(
            {
                "source_number": citation.get("source_number"),
                "citation_index": citation.get(
                    "citation_index", citation.get("source_number")
                ),
                "document_id": citation.get("document_id", citation.get("paper_id")),
                "document_version": citation.get("document_version"),
                "paper_id": citation.get("paper_id"),
                "arxiv_id": citation.get("arxiv_id"),
                "title": citation.get("title"),
                "chunk_id": citation.get("chunk_id"),
                "page": citation.get("page"),
                "section_title": citation.get("section_title"),
                "chunk_index": citation.get("chunk_index"),
                "score": citation.get("score"),
                "source_storage_key": citation.get("source_storage_key"),
                "start_char": citation.get("start_char"),
                "end_char": citation.get("end_char"),
            }
        )

    return citations


def _compact_sources(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    sources: list[dict[str, Any]] = []
    for source in value:
        if not isinstance(source, dict):
            continue

        sources.append(
            {
                "paper_source_number": source.get("paper_source_number"),
                "paper_id": source.get("paper_id"),
                "arxiv_id": source.get("arxiv_id"),
                "title": source.get("title"),
                "citation_numbers": source.get("citation_numbers", []),
            }
        )

    return sources


def _usage_metadata_fields(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_ms": None,
            "prefill_duration_ms": None,
            "decode_duration_ms": None,
            "model_load_duration_ms": None,
        }

    return {
        "input_tokens": _int_value(value.get("prompt_tokens")),
        "output_tokens": _int_value(value.get("completion_tokens")),
        "total_tokens": _int_value(value.get("total_tokens")),
        "latency_ms": _float_value(value.get("latency_ms")),
        "prefill_duration_ms": _float_value(value.get("prefill_duration_ms")),
        "decode_duration_ms": _float_value(value.get("decode_duration_ms")),
        "model_load_duration_ms": _float_value(
            value.get("model_load_duration_ms")
        ),
    }


def _int_value(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _derive_room_title(content: str, max_words: int = 7) -> str:
    words = " ".join(content.split()).split(" ")
    title = " ".join(words[:max_words]).strip()

    if len(words) > max_words:
        title = f"{title}..."

    return title or "New conversation"
