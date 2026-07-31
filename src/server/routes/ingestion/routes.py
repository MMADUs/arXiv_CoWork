# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from rag.service.arxiv import ArxivIngestionService
from rag.service.storage.interface import StorageProvider
from server.dependencies import get_db_session, get_s3_storage
from server.routes.ingestion.helpers import (
    download_papers,
    failed_download_count,
    successful_download_count,
)
from server.routes.ingestion.schema import (
    ArxivIngestRequest,
    ArxivIngestResponse,
    DownloadPapersRequest,
    DownloadPapersResponse,
    PaperIngestionItem,
)

router = APIRouter(prefix="/papers", tags=["paper-ingestion"])


@router.post("/ingest", response_model=ArxivIngestResponse)
async def ingest_arxiv_papers(
    request: ArxivIngestRequest,
    session: Session = Depends(get_db_session),
    storage: StorageProvider = Depends(get_s3_storage),
) -> ArxivIngestResponse:
    ingestion_service = ArxivIngestionService(session)

    try:
        query_params = request.to_arxiv_query_params()

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    try:
        ingestion_result = await ingestion_service.ingest_metadata(query_params)

    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
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
            ingestion_status=paper.ingestion_status,
            pdf_object_key=paper.pdf_object_key,
        )
        for paper in ingestion_result.papers
    ]

    if request.download_pdf:
        papers = await download_papers(
            paper_ids=[paper.paper_id for paper in papers],
            session=session,
            storage=storage,
        )

    return ArxivIngestResponse(
        papers_fetched=ingestion_result.papers_fetched,
        papers_stored=ingestion_result.papers_stored,
        download_pdf=request.download_pdf,
        pdfs_downloaded=(
            successful_download_count(papers) if request.download_pdf else 0
        ),
        pdfs_failed=failed_download_count(papers) if request.download_pdf else 0,
        papers=papers,
    )


@router.post("/ingest/pdf", response_model=DownloadPapersResponse)
async def download_arxiv_papers(
    request: DownloadPapersRequest,
    session: Session = Depends(get_db_session),
    storage: StorageProvider = Depends(get_s3_storage),
) -> DownloadPapersResponse:
    papers = await download_papers(
        paper_ids=request.paper_ids,
        session=session,
        storage=storage,
    )

    return DownloadPapersResponse(
        requested=len(request.paper_ids),
        downloaded=successful_download_count(papers),
        failed=failed_download_count(papers),
        papers=papers,
    )
