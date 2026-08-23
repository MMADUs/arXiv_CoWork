# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from rag.service.arxiv import (
    ArxivClient,
    ArxivIngestionService,
    ArxivNonRetryableError,
    ArxivRetryableError,
    ArxivServiceError,
)
from server.dependencies import get_arxiv_client, get_db_session
from server.routes.ingestion.ingestion_helpers import (
    enqueue_pdf_download_by_id,
    enqueue_ingested_pdf_downloads,
    enqueue_pending_pdf_downloads,
    queued_download_count,
    skipped_download_count,
    SUCCESSFUL_QUEUE,
)
from server.routes.ingestion.ingestion_schema import (
    PaperIngestionRequest,
    ArxivIngestResponse,
    DownloadPaperRequest,
    DownloadPaperResponse,
    DownloadPendingPapersRequest,
    PaperIngestionItem,
)

router = APIRouter(prefix="/papers", tags=["paper-ingestion"])


@router.post("/ingest", response_model=ArxivIngestResponse)
async def ingest_paper_route(
    request: PaperIngestionRequest,
    session: Session = Depends(get_db_session),
    arxiv_client: ArxivClient = Depends(get_arxiv_client),
) -> ArxivIngestResponse:
    ingestion_service = ArxivIngestionService(
        session=session,
        arxiv_client=arxiv_client,
    )

    try:
        query_params = request.to_arxiv_query_params()

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    try:
        ingestion_result = await ingestion_service.ingest_metadata(query_params)

    except ArxivNonRetryableError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    except ArxivRetryableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    except ArxivServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error

    papers = [
        PaperIngestionItem(
            paper_id=paper.paper_id,
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            authors=paper.authors,
            categories=paper.categories,
            published_date=paper.published_date,
        )
        for paper in ingestion_result.papers
    ]

    if request.download_pdf:
        try:
            papers = enqueue_ingested_pdf_downloads(
                paper_ids=[paper.paper_id for paper in papers],
                session=session,
            )

        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to enqueue PDF download tasks: {error}",
            ) from error

    return ArxivIngestResponse(
        papers_fetched=ingestion_result.papers_fetched,
        papers_stored=ingestion_result.papers_stored,
        download_pdf=request.download_pdf,
        pdf_downloads_queued=(
            queued_download_count(papers) if request.download_pdf else 0
        ),
        pdf_downloads_skipped=(
            skipped_download_count(papers) if request.download_pdf else 0
        ),
        papers=papers,
    )


@router.post(
    "/download-pdf",
    response_model=DownloadPaperResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def pending_pdf_download_route(
    request: DownloadPendingPapersRequest,
    session: Session = Depends(get_db_session),
) -> DownloadPaperResponse:
    try:
        papers = enqueue_pending_pdf_downloads(
            session=session,
            limit=request.limit,
            include_failed=request.include_failed,
        )

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to enqueue PDF download tasks: {error}",
        ) from error

    return DownloadPaperResponse(
        requested=len(papers),
        queued=queued_download_count(papers),
        skipped=skipped_download_count(papers),
        papers=papers,
    )


@router.post(
    "/{paper_id}/download-pdf",
    response_model=DownloadPaperResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def pdf_download_by_id_route(
    paper_id: UUID,
    request: DownloadPaperRequest,
    session: Session = Depends(get_db_session),
) -> DownloadPaperResponse:
    try:
        item = enqueue_pdf_download_by_id(
            paper_id=paper_id,
            session=session,
            force_download=request.force_download,
        )

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to enqueue PDF download task: {error}",
        ) from error

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper not found: {paper_id}",
        )

    return DownloadPaperResponse(
        requested=1,
        queued=1 if item.pdf_download_status == SUCCESSFUL_QUEUE else 0,
        skipped=0 if item.pdf_download_status == SUCCESSFUL_QUEUE else 1,
        papers=[item],
    )
