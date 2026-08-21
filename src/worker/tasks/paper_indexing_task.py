# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any
from uuid import UUID

from celery import Task

from rag.db.repository import PaperRepository
from rag.service.elasticsearch import ChunkIndexingService
from worker.celery_app import celery_app, INDEXING_ROUTE
from worker.queue_schema import IndexingQueue
from worker.instances import get_indexing_session, worker_async_run, get_db_session
from worker.tasks.common import (
    RetryableStageError,
    celery_settings,
    retry_or_fail,
    settings,
)


@celery_app.task(
    bind=True,
    name=INDEXING_ROUTE,
    max_retries=celery_settings.paper_indexing_max_retries,
)
def paper_indexing_task_route(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    task_payload = IndexingQueue.model_validate(payload)

    try:
        result = worker_async_run(_index_paper_chunks(self, task_payload))

    except ValueError as error:
        _mark_paper_indexing_failed(task_payload.paper_id, str(error))
        raise error

    except Exception as error:
        retry_error = RetryableStageError(str(error))

        retry_or_fail(
            self,
            retry_error,
            lambda: _mark_paper_indexing_failed(
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
            lambda: _mark_paper_indexing_failed(
                task_payload.paper_id,
                str(error),
            ),
        )

    return _trace_result(task_payload, result)


async def _index_paper_chunks(
    task: Task,
    task_payload: IndexingQueue,
) -> dict[str, Any]:
    include_failed_chunks = (
        task_payload.include_failed_chunks
        or int(getattr(task.request, "retries", 0)) > 0
    )

    with get_indexing_session(settings) as (
        session,
        embedding_provider,
        elasticsearch_client,
    ):
        paper_repository = PaperRepository(session)
        chunk_indexing_service = ChunkIndexingService(
            session=session,
            embedding_provider=embedding_provider,
            elasticsearch_client=elasticsearch_client,
        )

        paper = paper_repository.get_by_id(task_payload.paper_id)

        if paper is None:
            raise ValueError(f"Paper not found: {task_payload.paper_id}")

        metadata = {
            "paper_id": str(paper.id),
            "arxiv_id": paper.arxiv_id,
            "paper_title": paper.title,
        }

        if task_payload.force_reindex:
            result = await chunk_indexing_service.reindex_paper(task_payload.paper_id)

            return {
                **metadata,
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
            result = await chunk_indexing_service.index_pending_chunks(
                paper_id=task_payload.paper_id,
                limit=task_payload.batch_size,  # ok we somehow treat limit as batch, maybe make the docs soon
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
            **metadata,
            "batches": batches,
            "requested_chunks": requested_chunks,
            "indexed_chunks": indexed_chunks,
            "failed_chunks": failed_chunks,
            "errors": errors,
            "force_reindex": False,
        }


def _mark_paper_indexing_failed(paper_id: UUID, error: str | None = None) -> None:
    with get_db_session(settings) as session:
        paper_repository = PaperRepository(session)
        paper = paper_repository.get_by_id(paper_id)

        if paper is not None:
            paper_repository.mark_indexing_failed(paper, error)
            session.commit()


def _trace_result(task_payload: IndexingQueue, result: dict[str, Any]):
    return {
        **task_payload.to_task_payload(),
        "task_details": {
            "stage": "paper_indexing",
            "skipped": result["batches"] == 0,
            "detail": result,
        },
    }
