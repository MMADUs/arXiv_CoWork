# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

from celery import Task

from rag.db.model import PaperParserStatus
from rag.db.repository import PaperRepository
from rag.service.parser import PaperParsingService

from worker.celery_app import celery_app
from worker.payloads import PaperIndexingPayload
from worker.resources import worker_session
from worker.tasks.common import (
    RetryableStageError,
    StagePrerequisiteError,
    celery_settings,
    mark_paper_parse_failed,
    retry_or_fail,
    settings,
)


@celery_app.task(
    bind=True,
    name="worker.tasks.parse_paper",
    max_retries=celery_settings.parse_max_retries,
)
def parse_paper(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    task_payload = PaperIndexingPayload.model_validate(payload)

    try:
        with worker_session(settings) as (session, storage):
            paper = PaperRepository(session).get_by_id(task_payload.paper_id)

            if paper is None:
                raise StagePrerequisiteError(
                    f"Paper not found: {task_payload.paper_id}"
                )

            if paper.pdf_object_key is None:
                raise StagePrerequisiteError(
                    f"Paper has no stored PDF: {task_payload.paper_id}"
                )

            if (
                paper.parser_status == PaperParserStatus.PARSED
                and paper.parsed_json_object_key
                and not task_payload.force_parse
            ):
                return {
                    **task_payload.to_task_payload(),
                    "parse": {
                        "stage": "parse",
                        "skipped": True,
                        "detail": {
                            "parsed_json_object_key": paper.parsed_json_object_key,
                        },
                    },
                }

            result = PaperParsingService(
                session=session,
                storage=storage,
            ).parse_stored_pdf(task_payload.paper_id)

            return {
                **task_payload.to_task_payload(),
                "parse": {
                    "stage": "parse",
                    "skipped": False,
                    "detail": result,
                },
            }

    except StagePrerequisiteError:
        raise

    except ValueError as error:
        mark_paper_parse_failed(task_payload.paper_id, str(error))
        raise error

    except Exception as error:
        retry_error = RetryableStageError(str(error))

        retry_or_fail(
            self,
            retry_error,
            lambda: mark_paper_parse_failed(
                task_payload.paper_id,
                str(retry_error),
            ),
        )
        raise
