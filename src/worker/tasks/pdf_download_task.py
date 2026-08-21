# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any
from uuid import UUID

from celery import Task

from rag.db.model import PaperModel
from rag.db.repository import PaperRepository
from rag.service.arxiv import PaperDownloadService
from worker.celery_app import celery_app, PDF_DOWNLOAD_ROUTE
from worker.queue_schema import PdfDownloadQueue
from worker.instances import (
    get_pdf_download_session,
    worker_async_run,
    get_db_session,
)
from worker.tasks.common import (
    RetryableStageError,
    celery_settings,
    retry_or_fail,
    settings,
)


@celery_app.task(
    bind=True,
    name=PDF_DOWNLOAD_ROUTE,
    max_retries=celery_settings.pdf_download_max_retries,
)
def pdf_download_task_route(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    task_payload = PdfDownloadQueue.model_validate(payload)

    try:
        return worker_async_run(_download_paper_pdf(task_payload))

    except ValueError as error:
        _mark_paper_pdf_download_failed(task_payload.paper_id, str(error))
        raise error

    except Exception as error:
        retry_or_fail(
            self,
            RetryableStageError(str(error)),
            lambda: _mark_paper_pdf_download_failed(
                task_payload.paper_id,
                str(error),
            ),
        )
        raise


async def _download_paper_pdf(
    task_payload: PdfDownloadQueue,
) -> dict[str, Any]:
    with get_pdf_download_session(settings) as (session, storage, pdf_downloader):
        paper_repository = PaperRepository(session)
        paper_download_service = PaperDownloadService(
            session=session,
            storage=storage,
            pdf_downloader=pdf_downloader,
        )

        paper = paper_repository.get_by_id(task_payload.paper_id)

        if paper is None:
            raise ValueError(f"Paper not found: {task_payload.paper_id}")

        if paper.pdf_object_key and not task_payload.force_download:
            return _trace_result(task_payload, paper, skipped=True)

        paper_repository.mark_pdf_download_started(paper)
        session.commit()

        _pdf_object_key = await paper_download_service.download_pdf_to_storage(
            task_payload.paper_id
        )

        return _trace_result(task_payload, paper, skipped=False)


def _mark_paper_pdf_download_failed(paper_id: UUID, error: str) -> None:
    with get_db_session(settings) as session:
        paper_repository = PaperRepository(session)
        paper = paper_repository.get_by_id(paper_id)

        if paper is not None:
            paper_repository.mark_pdf_download_failed(paper, error)
            session.commit()


def _trace_result(
    task_payload: PdfDownloadQueue, paper: PaperModel, skipped: bool
) -> dict[str, Any]:
    return {
        **task_payload.to_task_payload(),
        "task_details": {
            "stage": "download_pdf",
            "skipped": skipped,
            "detail": {
                "paper_id": str(paper.id),
                "arxiv_id": paper.arxiv_id,
                "paper_title": paper.title,
                "pdf_object_key": paper.pdf_object_key,
            },
        },
    }
