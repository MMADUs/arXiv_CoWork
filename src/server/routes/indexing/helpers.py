# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from worker.payloads import PaperIndexingPayload
from worker.workflow import enqueue_paper_indexing_workflow

from server.routes.indexing.schema import IndexPaperRequest


def enqueue_indexing_workflow(
    paper_id: UUID,
    request: IndexPaperRequest,
) -> str:
    payload = PaperIndexingPayload(
        paper_id=paper_id,
        force_parse=request.force_parse,
        force_chunk=request.force_chunk,
        force_reindex=request.force_reindex,
        include_failed_chunks=request.include_failed_chunks,
        batch_size=request.batch_size,
    )

    return enqueue_paper_indexing_workflow(payload)
