# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from rag.db.model import PaperChunkingStatus, PaperIndexingStatus, PaperParserStatus
from rag.db.repository import PaperRepository

from server.dependencies import get_db_session
from server.routes.indexing.indexing_helpers import (
    enqueue_indexing_by_id,
    enqueue_pending_indexing,
    queued_index_count,
    skipped_index_count,
)
from server.routes.indexing.indexing_schema import (
    IndexPaperRequest,
    IndexPaperResponse,
    IndexPapersResponse,
    IndexPendingPapersRequest,
)

router = APIRouter(prefix="/papers", tags=["paper-indexing"])


@router.post(
    "/index",
    response_model=IndexPapersResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def pending_indexing_route(
    request: IndexPendingPapersRequest,
    session: Session = Depends(get_db_session),
) -> IndexPapersResponse:
    try:
        papers = enqueue_pending_indexing(
            request=request,
            session=session,
        )

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to enqueue paper indexing workflows: {error}",
        ) from error

    return IndexPapersResponse(
        requested=len(papers),
        queued=queued_index_count(papers),
        skipped=skipped_index_count(papers),
        papers=papers,
    )


@router.post(
    "/{paper_id}/index",
    response_model=IndexPaperResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def indexing_by_id_route(
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

    if paper.parser_status == PaperParserStatus.PARSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Paper parsing is already in progress: {paper_id}",
        )

    if paper.chunking_status == PaperChunkingStatus.CHUNKING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Paper chunking is already in progress: {paper_id}",
        )

    if paper.indexing_status == PaperIndexingStatus.INDEXING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Paper indexing is already in progress: {paper_id}",
        )

    if paper.indexing_status == PaperIndexingStatus.INDEXED and not (
        request.force_parse or request.force_chunk or request.force_reindex
    ):
        return IndexPaperResponse(
            paper_id=paper_id,
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            task_id=None,
            status="already_indexed",
        )

    if paper.pdf_object_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Paper has no stored PDF: {paper_id}",
        )

    try:
        task_id = enqueue_indexing_by_id(paper_id=paper_id, request=request)

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to enqueue paper indexing workflow: {error}",
        ) from error

    return IndexPaperResponse(
        paper_id=paper_id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        task_id=task_id,
        status="queued",
    )
