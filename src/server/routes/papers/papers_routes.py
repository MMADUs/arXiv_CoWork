# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from math import ceil
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from rag.db.repository import ChunkRepository, PaperRepository
from server.dependencies import get_db_session
from server.routes.papers.papers_helpers import build_paper_response
from server.routes.papers.papers_schema import PaperDetailResponse, PaperListResponse

router = APIRouter(prefix="/papers", tags=["manage-paper"])


@router.get("", response_model=PaperListResponse)
def get_all_papers(
    output: Literal["compact", "full"] = "compact",
    status_filter: Literal["failed"] | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> PaperListResponse:
    paper_repository = PaperRepository(session)
    chunk_repository = ChunkRepository(session)

    offset = (page - 1) * page_size

    if status_filter == "failed":
        papers, total = paper_repository.list_failed_page(
            limit=page_size,
            offset=offset,
        )
    else:
        papers, total = paper_repository.list_recent_page(
            limit=page_size,
            offset=offset,
        )

    chunk_errors_by_paper_id = {}

    if output == "full":
        chunk_errors_by_paper_id = chunk_repository.chunk_error_summaries_by_paper_ids(
            paper.id for paper in papers
        )

    return PaperListResponse(
        output=output,
        status=status_filter,
        count=len(papers),
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
        offset=offset,
        papers=[
            build_paper_response(
                paper=paper,
                output=output,
                chunk_errors=chunk_errors_by_paper_id.get(paper.id, []),
            )
            for paper in papers
        ],
    )


@router.get("/{paper_id}", response_model=PaperDetailResponse)
def get_arxiv_paper(
    paper_id: UUID,
    output: Literal["compact", "full"] = "compact",
    session: Session = Depends(get_db_session),
) -> PaperDetailResponse:
    paper_repository = PaperRepository(session)
    chunk_repository = ChunkRepository(session)

    paper = paper_repository.get_by_id(paper_id)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )

    chunk_errors = []

    if output == "full":
        chunk_errors = chunk_repository.chunk_error_summaries_by_paper_ids(
            [paper.id]
        ).get(paper.id, [])

    return PaperDetailResponse(
        output=output,
        paper=build_paper_response(
            paper=paper,
            output=output,
            chunk_errors=chunk_errors,
        ),
    )
