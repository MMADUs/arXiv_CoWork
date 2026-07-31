# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import get_settings

from worker.celery_app import celery_app
from worker.payloads import PaperIndexingPayload


def enqueue_paper_indexing_workflow(payload: PaperIndexingPayload) -> str:
    celery_settings = get_settings().celery_settings

    task_payload = payload.to_task_payload()

    workflow = (
        celery_app.signature(
            "worker.tasks.parse_paper",
            args=[task_payload],
            queue=celery_settings.parsing_queue,
        )
        | celery_app.signature(
            "worker.tasks.chunk_paper",
            queue=celery_settings.chunking_queue,
        )
        | celery_app.signature(
            "worker.tasks.index_paper_chunks",
            queue=celery_settings.indexing_queue,
        )
    )

    result = workflow.apply_async()

    return str(result.id)
