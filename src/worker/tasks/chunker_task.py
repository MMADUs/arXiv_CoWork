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
    StagePrerequisiteError,
    celery_settings,
    mark_paper_chunking_failed,
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

    except StagePrerequisiteError:
        raise

    except ValueError as error:
        mark_paper_chunking_failed(task_payload.paper_id, str(error))
        raise error

    except Exception as error:
        retry_error = RetryableStageError(str(error))

        retry_or_fail(
            self,
            retry_error,
            lambda: mark_paper_chunking_failed(
                task_payload.paper_id,
                str(retry_error),
            ),
        )
        raise
