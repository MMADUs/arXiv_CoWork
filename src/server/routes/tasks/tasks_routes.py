# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import APIRouter

from server.routes.tasks.tasks_schema import TaskStatusResponse
from worker.celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    result = celery_app.AsyncResult(task_id)
    failed = result.failed()

    return TaskStatusResponse(
        task_id=task_id,
        state=result.state,
        ready=result.ready(),
        successful=result.successful(),
        failed=failed,
        result=None if failed else result.result if result.ready() else None,
        error=str(result.result) if failed else None,
    )
