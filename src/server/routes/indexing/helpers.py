# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from sqlalchemy.orm import Session

from rag.db.model import PaperIndexingStatus, PaperModel
from rag.db.repository import PaperRepository
from worker.payloads import PaperIndexingPayload
from worker.workflow import enqueue_paper_indexing_workflow

from server.routes.indexing.schema import (
    IndexPaperItem,
    IndexPaperRequest,
    IndexPendingPapersRequest,
)


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


def enqueue_pending_indexing_workflows(
    request: IndexPendingPapersRequest,
    session: Session,
) -> list[IndexPaperItem]:
    paper_repository = PaperRepository(session)
    papers = paper_repository.list_pending_indexing_papers(
        limit=request.limit,
        include_failed=request.include_failed_chunks,
    )

    return [
        enqueue_indexing_workflow_for_paper(
            paper=paper,
            paper_repository=paper_repository,
            request=request,
            session=session,
        )
        for paper in papers
    ]


def enqueue_indexing_workflow_for_paper(
    paper: PaperModel,
    paper_repository: PaperRepository,
    request: IndexPaperRequest,
    session: Session,
) -> IndexPaperItem:
    if paper.indexing_status == PaperIndexingStatus.INDEXING:
        return _index_item(
            paper=paper,
            task_id=None,
            status="already_indexing",
        )

    if (
        paper.indexing_status == PaperIndexingStatus.INDEXED
        and not request.force_reindex
    ):
        return _index_item(
            paper=paper,
            task_id=None,
            status="already_indexed",
        )

    if paper.pdf_object_key is None:
        return _index_item(
            paper=paper,
            task_id=None,
            status="no_pdf",
        )

    paper_repository.mark_indexing_started(paper)
    session.commit()

    try:
        task_id = enqueue_indexing_workflow(
            paper_id=paper.id,
            request=request,
        )

    except Exception:
        paper_repository.mark_indexing_failed(paper)
        session.commit()
        raise

    return _index_item(
        paper=paper,
        task_id=task_id,
        status="queued",
    )


def queued_index_count(items: list[IndexPaperItem]) -> int:
    return sum(1 for item in items if item.status == "queued")


def skipped_index_count(items: list[IndexPaperItem]) -> int:
    return sum(1 for item in items if item.status != "queued")


def _index_item(
    paper: PaperModel,
    task_id: str | None,
    status: str,
) -> IndexPaperItem:
    return IndexPaperItem(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        indexing_status=paper.indexing_status,
        task_id=task_id,
        status=status,
    )
