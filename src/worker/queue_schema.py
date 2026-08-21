# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from pydantic import BaseModel, Field


class PdfDownloadQueue(BaseModel):
    """
    PDF Download queue payload schema
    """

    paper_id: UUID
    force_download: bool = False

    def to_task_payload(self) -> dict[str, object]:
        data = self.model_dump()
        data["paper_id"] = str(self.paper_id)
        return data


class IndexingQueue(BaseModel):
    """
    Paper indexing queue payload schema
    """

    paper_id: UUID
    force_parse: bool = False
    force_chunk: bool = False
    force_reindex: bool = False
    include_failed_chunks: bool = False
    batch_size: int = Field(default=50, ge=1, le=500)

    def to_task_payload(self) -> dict[str, object]:
        data = self.model_dump()
        data["paper_id"] = str(self.paper_id)
        return data


class StageResult(BaseModel):
    stage: str
    skipped: bool = False
    detail: dict[str, object] = Field(default_factory=dict)
