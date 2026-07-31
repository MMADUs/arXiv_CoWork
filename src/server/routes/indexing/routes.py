# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from rag.db.model import PaperIndexingStatus
from rag.db.repository import PaperRepository

from server.dependencies import get_db_session
from server.routes.indexing.helpers import enqueue_indexing_workflow
from server.routes.indexing.schema import IndexPaperRequest, IndexPaperResponse

router = APIRouter(prefix="/papers", tags=["paper-indexing"])


@router.post(
    "/{paper_id}/index",
    response_model=IndexPaperResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_arxiv_paper_indexing(
    paper_id: UUID,
    request: IndexPaperRequest,
    session: Session = Depends(get_db_session),
) -> IndexPaperResponse:
    paper_repository = PaperRepository(session)

    paper = paper_repository.get_by_id_for_update(paper_id)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )

    if paper.indexing_status == PaperIndexingStatus.INDEXING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Paper indexing is already in progress: {paper_id}",
        )

    if (
        paper.indexing_status == PaperIndexingStatus.INDEXED
        and not request.force_reindex
    ):
        return IndexPaperResponse(
            paper_id=paper_id,
            task_id=None,
            status="already_indexed",
        )

    if paper.pdf_object_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Paper has no stored PDF: {paper_id}",
        )

    paper_repository.mark_indexing_started(paper)
    session.commit()

    try:
        task_id = enqueue_indexing_workflow(paper_id=paper_id, request=request)

    except Exception as error:
        paper_repository.mark_indexing_failed(paper)
        session.commit()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to enqueue paper indexing workflow: {error}",
        ) from error

    return IndexPaperResponse(
        paper_id=paper_id,
        task_id=task_id,
        status="queued",
    )
