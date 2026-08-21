# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import get_settings

from worker.celery_app import (
    celery_app,
    PDF_DOWNLOAD_ROUTE,
    PARSING_ROUTE,
    CHUNKING_ROUTE,
    INDEXING_ROUTE,
)
from worker.queue_schema import IndexingQueue, PdfDownloadQueue


def enqueue_paper_pdf_download(payload: PdfDownloadQueue) -> str:
    """
    Enqueue paper to celery async paper pdf download task

    Returns:
        Task id made by celery
    """
    celery_settings = get_settings().celery_settings

    result = celery_app.signature(
        PDF_DOWNLOAD_ROUTE,
        args=[payload.to_task_payload()],
        queue=celery_settings.pdf_download_queue,
    ).apply_async()

    return str(result.id)


def enqueue_indexing_workflow(payload: IndexingQueue) -> str:
    """
    Enqueue paper to celery async paper indexing workflow

    Returns:
        Task id made by celery
    """
    celery_settings = get_settings().celery_settings

    task_payload = payload.to_task_payload()

    workflow = (
        celery_app.signature(
            PARSING_ROUTE,
            args=[task_payload],
            queue=celery_settings.parsing_queue,
        )
        | celery_app.signature(
            CHUNKING_ROUTE,
            queue=celery_settings.chunking_queue,
        )
        | celery_app.signature(
            INDEXING_ROUTE,
            queue=celery_settings.indexing_queue,
        )
    )

    result = workflow.apply_async()

    return str(result.id)
