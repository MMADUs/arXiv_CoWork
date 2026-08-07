# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

from celery import Task

from rag.service.elasticsearch import ChunkIndexingService
from worker.celery_app import celery_app
from worker.payloads import PaperIndexingPayload
from worker.resources import indexing_resources, worker_async_run
from worker.tasks.common import (
    RetryableStageError,
    celery_settings,
    mark_paper_indexing_failed,
    retry_or_fail,
    settings,
)


@celery_app.task(
    bind=True,
    name="worker.tasks.index_paper_chunks",
    max_retries=celery_settings.index_max_retries,
)
def index_paper_chunks(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    task_payload = PaperIndexingPayload.model_validate(payload)

    try:
        result = worker_async_run(_index_paper_chunks(self, task_payload))

    except ValueError as error:
        mark_paper_indexing_failed(task_payload.paper_id, str(error))
        raise error

    except Exception as error:
        retry_error = RetryableStageError(str(error))

        retry_or_fail(
            self,
            retry_error,
            lambda: mark_paper_indexing_failed(
                task_payload.paper_id,
                str(retry_error),
            ),
        )
        raise

    if result["failed_chunks"]:
        error = RetryableStageError(
            f"Failed to index {result['failed_chunks']} chunk(s)"
        )
        retry_or_fail(
            self,
            error,
            lambda: mark_paper_indexing_failed(
                task_payload.paper_id,
                str(error),
            ),
        )

    return {
        **task_payload.to_task_payload(),
        "index": {
            "stage": "index",
            "skipped": result["batches"] == 0,
            "detail": result,
        },
    }


async def _index_paper_chunks(
    task: Task,
    task_payload: PaperIndexingPayload,
) -> dict[str, Any]:
    include_failed_chunks = (
        task_payload.include_failed_chunks
        or int(getattr(task.request, "retries", 0)) > 0
    )

    with indexing_resources(settings) as (
        session,
        _storage,
        embedding_provider,
        elasticsearch_client,
    ):
        service = ChunkIndexingService(
            session=session,
            embedding_provider=embedding_provider,
            elasticsearch_client=elasticsearch_client,
        )

        if task_payload.force_reindex:
            result = await service.reindex_paper(task_payload.paper_id)
            return {
                "batches": 1,
                "requested_chunks": result["chunks_requested"],
                "indexed_chunks": result["chunks_indexed"],
                "failed_chunks": result["chunks_failed"],
                "errors": result["errors"],
                "force_reindex": True,
            }

        batches = 0
        requested_chunks = 0
        indexed_chunks = 0
        failed_chunks = 0
        errors: dict[str, str] = {}

        while True:
            result = await service.index_pending_chunks(
                paper_id=task_payload.paper_id,
                limit=task_payload.batch_size,
                include_failed=include_failed_chunks,
            )

            if result.requested_chunks == 0:
                break

            batches += 1
            requested_chunks += result.requested_chunks
            indexed_chunks += result.indexed_chunks
            failed_chunks += result.failed_chunks
            errors.update({str(key): value for key, value in result.errors.items()})

            if result.failed_chunks:
                break

            include_failed_chunks = False

        return {
            "batches": batches,
            "requested_chunks": requested_chunks,
            "indexed_chunks": indexed_chunks,
            "failed_chunks": failed_chunks,
            "errors": errors,
            "force_reindex": False,
        }
