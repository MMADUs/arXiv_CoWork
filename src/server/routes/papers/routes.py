# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from rag.db.repository import PaperRepository
from server.dependencies import get_db_session
from server.routes.papers.helpers import paper_response
from server.routes.papers.schema import PaperDetailResponse, PaperListResponse

router = APIRouter(prefix="/papers", tags=["manage-paper"])


@router.get("", response_model=PaperListResponse)
def list_arxiv_papers(
    output: Literal["compact", "full"] = "compact",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> PaperListResponse:
    paper_repository = PaperRepository(session)
    papers = paper_repository.list_recent(limit=limit, offset=offset)

    return PaperListResponse(
        output=output,
        count=len(papers),
        limit=limit,
        offset=offset,
        papers=[paper_response(paper, output) for paper in papers],
    )


@router.get("/{paper_id}", response_model=PaperDetailResponse)
def get_arxiv_paper(
    paper_id: UUID,
    output: Literal["compact", "full"] = "compact",
    session: Session = Depends(get_db_session),
) -> PaperDetailResponse:
    paper_repository = PaperRepository(session)
    paper = paper_repository.get_by_id(paper_id)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )

    return PaperDetailResponse(
        output=output,
        paper=paper_response(paper, output),
    )
