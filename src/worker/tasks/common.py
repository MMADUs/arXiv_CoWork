# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from collections.abc import Callable
from uuid import UUID

from celery import Task

from rag.config import get_settings
from rag.db.repository import PaperRepository
from worker.resources import worker_db_session

settings = get_settings()
celery_settings = settings.celery_settings


class RetryableStageError(RuntimeError):
    pass


def retry_or_fail(
    task: Task,
    error: Exception,
    on_exhausted: Callable[[], None],
) -> None:
    if int(getattr(task.request, "retries", 0)) >= int(task.max_retries or 0):
        on_exhausted()
        raise error

    raise task.retry(exc=error, countdown=_retry_countdown(task))


def mark_paper_parse_failed(paper_id: UUID, error: str) -> None:
    with worker_db_session(settings) as session:
        paper_repository = PaperRepository(session)
        paper = paper_repository.get_by_id(paper_id)

        if paper is not None:
            paper_repository.mark_parse_failed(paper, error)
            session.commit()


def mark_paper_indexing_failed(paper_id: UUID) -> None:
    with worker_db_session(settings) as session:
        paper_repository = PaperRepository(session)
        paper = paper_repository.get_by_id(paper_id)

        if paper is not None:
            paper_repository.mark_indexing_failed(paper)
            session.commit()


def _retry_countdown(task: Task) -> int:
    retry_number = int(getattr(task.request, "retries", 0)) + 1
    countdown = celery_settings.retry_backoff_seconds * (2 ** (retry_number - 1))
    return min(countdown, celery_settings.retry_backoff_max_seconds)
