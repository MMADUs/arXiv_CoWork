# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any
from uuid import UUID

from celery import Task

from rag.db.model import PaperModel
from rag.db.repository import ChunkRepository, PaperRepository
from rag.service.chunker import PaperChunkingService

from worker.celery_app import celery_app, CHUNKING_ROUTE
from worker.queue_schema import IndexingQueue
from worker.instances import get_db_storage_session, get_db_session
from worker.tasks.common import (
    RetryableStageError,
    StagePrerequisiteError,
    celery_settings,
    retry_or_fail,
    settings,
)


@celery_app.task(
    bind=True,
    name=CHUNKING_ROUTE,
    max_retries=celery_settings.paper_chunking_max_retries,
)
def paper_chunker_task_route(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    task_payload = IndexingQueue.model_validate(payload)

    try:
        with get_db_storage_session(settings) as (session, storage):
            paper_repository = PaperRepository(session)
            chunk_repository = ChunkRepository(session)
            paper_chunking_service = PaperChunkingService(
                session=session,
                storage=storage,
            )

            paper = paper_repository.get_by_id(task_payload.paper_id)

            if paper is None:
                raise StagePrerequisiteError(
                    f"Paper not found: {task_payload.paper_id}"
                )

            if paper.parsed_json_object_key is None:
                raise StagePrerequisiteError(
                    f"Paper has no parsed JSON artifact: {task_payload.paper_id}"
                )

            chunks = chunk_repository.list_by_paper_id(task_payload.paper_id)

            should_skip = bool(chunks) and not (
                task_payload.force_chunk or task_payload.force_parse
            )

            if should_skip:
                paper_repository.mark_chunked(paper)
                session.commit()

                return _trace_result(
                    task_payload,
                    paper,
                    created_chunks=0,
                    skipped=True,
                )

            inserted_chunks = paper_chunking_service.chunk_parsed_paper(
                task_payload.paper_id
            )

            return _trace_result(
                task_payload,
                paper,
                created_chunks=inserted_chunks,
                skipped=False,
            )

    except StagePrerequisiteError:
        raise

    except ValueError as error:
        _mark_paper_chunking_failed(task_payload.paper_id, str(error))
        raise error

    except Exception as error:
        retry_error = RetryableStageError(str(error))

        retry_or_fail(
            self,
            retry_error,
            lambda: _mark_paper_chunking_failed(
                task_payload.paper_id,
                str(retry_error),
            ),
        )
        raise


def _mark_paper_chunking_failed(paper_id: UUID, error: str) -> None:
    with get_db_session(settings) as session:
        paper_repository = PaperRepository(session)
        paper = paper_repository.get_by_id(paper_id)

        if paper is not None:
            paper_repository.mark_chunking_failed(paper, error)
            session.commit()


def _trace_result(
    task_payload: IndexingQueue,
    paper: PaperModel,
    created_chunks: int,
    skipped: bool,
) -> dict[str, Any]:
    return {
        **task_payload.to_task_payload(),
        "task_details": {
            "stage": "paper_chunking",
            "skipped": skipped,
            "detail": {
                "paper_id": str(paper.id),
                "arxiv_id": paper.arxiv_id,
                "paper_title": paper.title,
                "created_chunks": created_chunks,
            },
        },
    }
