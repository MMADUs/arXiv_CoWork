# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from sqlalchemy.orm import Session

from rag.db.model import (
    PaperChunkingStatus,
    PaperIndexingStatus,
    PaperModel,
    PaperParserStatus,
)
from rag.db.repository import PaperRepository
from worker.queue_schema import IndexingQueue
from worker.workflow import enqueue_indexing_workflow

from server.routes.indexing.indexing_schema import (
    IndexPaperItem,
    IndexPaperRequest,
    IndexPendingPapersRequest,
)


def enqueue_indexing_by_id(
    paper_id: UUID,
    request: IndexPaperRequest,
) -> str:
    """
    Enqueue indexing task by paper id to worker workflow
    """
    payload = IndexingQueue(
        paper_id=paper_id,
        force_parse=request.force_parse,
        force_chunk=request.force_chunk,
        force_reindex=request.force_reindex,
        include_failed_chunks=request.include_failed_chunks,
        batch_size=request.batch_size,
    )

    return enqueue_indexing_workflow(payload)


def enqueue_paper(
    paper: PaperModel,
    request: IndexPaperRequest,
) -> IndexPaperItem:
    if paper.parser_status == PaperParserStatus.PARSING:
        return _return_item(
            paper=paper,
            task_id=None,
            status="already_parsing",
        )

    if paper.chunking_status == PaperChunkingStatus.CHUNKING:
        return _return_item(
            paper=paper,
            task_id=None,
            status="already_chunking",
        )

    if paper.indexing_status == PaperIndexingStatus.INDEXING:
        return _return_item(
            paper=paper,
            task_id=None,
            status="already_indexing",
        )

    if paper.indexing_status == PaperIndexingStatus.INDEXED and not (
        request.force_parse or request.force_chunk or request.force_reindex
    ):
        return _return_item(
            paper=paper,
            task_id=None,
            status="already_indexed",
        )

    if paper.pdf_object_key is None:
        return _return_item(
            paper=paper,
            task_id=None,
            status="no_pdf",
        )

    task_id = enqueue_indexing_by_id(paper_id=paper.id, request=request)

    return _return_item(
        paper=paper,
        task_id=task_id,
        status="queued",
    )


def enqueue_pending_indexing(
    request: IndexPendingPapersRequest,
    session: Session,
) -> list[IndexPaperItem]:
    """
    Enqueue all pending indexing paper to worker workflow
    """
    paper_repository = PaperRepository(session)

    papers = paper_repository.list_pending_indexing_papers(
        limit=request.limit,
        include_failed=request.include_failed_chunks,
    )

    return [enqueue_paper(paper=paper, request=request) for paper in papers]


def _return_item(
    paper: PaperModel,
    task_id: str | None,
    status: str,
) -> IndexPaperItem:
    return IndexPaperItem(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        parser_status=paper.parser_status,
        chunking_status=paper.chunking_status,
        indexing_status=paper.indexing_status,
        task_id=task_id,
        status=status,
    )


def queued_index_count(items: list[IndexPaperItem]) -> int:
    return sum(1 for item in items if item.status == "queued")


def skipped_index_count(items: list[IndexPaperItem]) -> int:
    return sum(1 for item in items if item.status != "queued")
