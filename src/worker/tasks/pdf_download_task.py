# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

from celery import Task

from rag.db.repository import PaperRepository
from rag.service.arxiv import PaperDownloadService
from worker.celery_app import celery_app
from worker.payloads import PaperPdfDownloadPayload
from worker.resources import pdf_download_resources, worker_async_run
from worker.tasks.common import (
    RetryableStageError,
    celery_settings,
    mark_paper_pdf_download_failed,
    retry_or_fail,
    settings,
)


@celery_app.task(
    bind=True,
    name="worker.tasks.download_paper_pdf",
    max_retries=celery_settings.pdf_download_max_retries,
)
def download_paper_pdf(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    task_payload = PaperPdfDownloadPayload.model_validate(payload)

    try:
        return worker_async_run(_download_paper_pdf(task_payload))

    except ValueError as error:
        mark_paper_pdf_download_failed(task_payload.paper_id, str(error))
        raise error

    except Exception as error:
        retry_or_fail(
            self,
            RetryableStageError(str(error)),
            lambda: mark_paper_pdf_download_failed(
                task_payload.paper_id,
                str(error),
            ),
        )
        raise


async def _download_paper_pdf(
    task_payload: PaperPdfDownloadPayload,
) -> dict[str, Any]:
    with pdf_download_resources(settings) as (session, storage, pdf_downloader):
        paper_repository = PaperRepository(session)
        paper = paper_repository.get_by_id(task_payload.paper_id)

        if paper is None:
            raise ValueError(f"Paper not found: {task_payload.paper_id}")

        if paper.pdf_object_key and not task_payload.force_download:
            return {
                **task_payload.to_task_payload(),
                "download": {
                    "stage": "download_pdf",
                    "skipped": True,
                    "detail": {
                        "pdf_object_key": paper.pdf_object_key,
                    },
                },
            }

        paper_repository.mark_pdf_download_started(paper)
        session.commit()

        pdf_object_key = await PaperDownloadService(
            session=session,
            storage=storage,
            pdf_downloader=pdf_downloader,
        ).download_pdf_to_storage(task_payload.paper_id)

        return {
            **task_payload.to_task_payload(),
            "download": {
                "stage": "download_pdf",
                "skipped": False,
                "detail": {
                    "pdf_object_key": pdf_object_key,
                },
            },
        }
