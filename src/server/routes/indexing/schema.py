# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class IndexPaperRequest(BaseModel):
    force_parse: bool = False
    force_chunk: bool = False
    force_reindex: bool = False
    include_failed_chunks: bool = False
    batch_size: int = Field(default=50, ge=1, le=500)


class IndexPaperResponse(BaseModel):
    paper_id: UUID
    task_id: str | None
    status: Literal["queued", "already_indexed"]
