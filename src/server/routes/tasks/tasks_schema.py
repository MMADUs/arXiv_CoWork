# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

from pydantic import BaseModel


class TaskStatusResponse(BaseModel):
    """
    Route response schema for reading Celery task status.
    """

    task_id: str
    state: str
    ready: bool
    successful: bool
    failed: bool
    result: Any | None = None
    error: str | None = None
