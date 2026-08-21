# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from collections.abc import Callable

from celery import Task

from rag.config import get_settings

settings = get_settings()
celery_settings = settings.celery_settings


class RetryableStageError(RuntimeError):
    """Runtime error exception for a retryable failure at certain stage"""

    pass


class StagePrerequisiteError(RuntimeError):
    """Runtime error exception when a data gets processed when its prior stages failed"""

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


def _retry_countdown(task: Task) -> int:
    retry_number = int(getattr(task.request, "retries", 0)) + 1
    countdown = celery_settings.retry_backoff_seconds * (2 ** (retry_number - 1))
    return min(countdown, celery_settings.retry_backoff_max_seconds)
