# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

from celery import Task

from rag.db.repository import ChunkRepository, PaperRepository
from rag.service.chunker import PaperChunkingService

from worker.celery_app import celery_app
from worker.payloads import PaperIndexingPayload
from worker.resources import worker_session
from worker.tasks.common import (
    RetryableStageError,
    celery_settings,
    mark_paper_indexing_failed,
    retry_or_fail,
    settings,
)


@celery_app.task(
    bind=True,
    name="worker.tasks.chunk_paper",
    max_retries=celery_settings.chunk_max_retries,
)
def chunk_paper(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    task_payload = PaperIndexingPayload.model_validate(payload)

    try:
        with worker_session(settings) as (session, storage):
            paper_repository = PaperRepository(session)
            chunk_repository = ChunkRepository(session)

            paper = paper_repository.get_by_id(task_payload.paper_id)

            if paper is None:
                raise ValueError(f"Paper not found: {task_payload.paper_id}")

            if paper.parsed_json_object_key is None:
                raise ValueError(
                    f"Paper has no parsed JSON artifact: {task_payload.paper_id}"
                )

            chunks = chunk_repository.list_by_paper_id(task_payload.paper_id)
            
            should_skip = bool(chunks) and not (
                task_payload.force_chunk or task_payload.force_parse
            )

            if should_skip:
                return {
                    **task_payload.to_task_payload(),
                    "chunk": {
                        "stage": "chunk",
                        "skipped": True,
                        "detail": {"chunks_existing": len(chunks)},
                    },
                }

            result = PaperChunkingService(
                session=session,
                storage=storage,
            ).chunk_parsed_paper(task_payload.paper_id)

            return {
                **task_payload.to_task_payload(),
                "chunk": {
                    "stage": "chunk",
                    "skipped": False,
                    "detail": result,
                },
            }

    except ValueError as error:
        mark_paper_indexing_failed(task_payload.paper_id)
        raise error

    except Exception as error:
        retry_or_fail(
            self,
            RetryableStageError(str(error)),
            lambda: mark_paper_indexing_failed(task_payload.paper_id),
        )
        raise
