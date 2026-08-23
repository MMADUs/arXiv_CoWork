# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any
from uuid import UUID

from celery import Task

from rag.db.model import PaperParserStatus, PaperModel
from rag.db.repository import PaperRepository
from rag.service.parser import (
    PaperParsingService,
    ParserNonRetryableError,
    ParserRetryableError,
)

from worker.celery_app import PARSING_ROUTE, celery_app
from worker.instances import get_db_session, get_db_storage_session
from worker.queue_schema import IndexingQueue
from worker.tasks.common import (
    RetryableStageError,
    StagePrerequisiteError,
    celery_settings,
    retry_or_fail,
    settings,
)


@celery_app.task(
    bind=True,
    name=PARSING_ROUTE,
    max_retries=celery_settings.paper_parsing_max_retries,
)
def paper_parser_task_route(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    task_payload = IndexingQueue.model_validate(payload)

    try:
        with get_db_storage_session(settings) as (session, storage):
            paper_repository = PaperRepository(session)
            paper_parsing_service = PaperParsingService(
                session=session,
                storage=storage,
            )

            paper = paper_repository.get_by_id(task_payload.paper_id)

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
                return _trace_result(
                    task_payload,
                    paper,
                    parser_name=None,
                    skipped=True,
                )

            parser_name = paper_parsing_service.parse_stored_pdf(task_payload.paper_id)

            return _trace_result(
                task_payload,
                paper,
                parser_name,
                skipped=False,
            )

    except StagePrerequisiteError:
        raise

    except ParserNonRetryableError as error:
        _mark_paper_parse_failed(task_payload.paper_id, str(error))
        raise

    except ParserRetryableError as error:
        retry_or_fail(
            self,
            RetryableStageError(str(error)),
            lambda: _mark_paper_parse_failed(
                task_payload.paper_id,
                str(error),
            ),
        )


def _mark_paper_parse_failed(paper_id: UUID, error: str) -> None:
    with get_db_session(settings) as session:
        paper_repository = PaperRepository(session)
        paper = paper_repository.get_by_id(paper_id)

        if paper is not None:
            paper_repository.mark_parse_failed(paper, error)
            session.commit()


def _trace_result(
    task_payload: IndexingQueue,
    paper: PaperModel,
    parser_name: str | None,
    skipped: bool,
) -> dict[str, Any]:
    return {
        **task_payload.to_task_payload(),
        "task_details": {
            "stage": "paper_parsing",
            "skipped": skipped,
            "detail": {
                "paper_id": str(paper.id),
                "arxiv_id": paper.arxiv_id,
                "paper_title": paper.title,
                "parser_name": parser_name,
                "pdf_object_key": paper.pdf_object_key,
                "parsed_json_object_key": paper.parsed_json_object_key,
            },
        },
    }
