# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from rag.db.config import get_db_session
from rag.db.model import PaperModel
from rag.db.repository import PaperRepository
from rag.routes.arxiv.arxiv_schema import (
    ArxivIngestRequest,
    ArxivIngestResponse,
    CompactPaperResponse,
    DownloadPapersRequest,
    DownloadPapersResponse,
    FullPaperResponse,
    PaperDetailResponse,
    PaperIngestionItem,
    PaperListResponse,
)
from rag.service.arxiv import ArxivIngestionService, PaperDownloadService
from rag.service.storage import StorageProvider, get_s3_storage

router = APIRouter(prefix="/arxiv", tags=["arxiv"])


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
        papers = await _download_papers(
            paper_ids=[paper.paper_id for paper in papers],
            session=session,
            storage=storage,
        )

    return ArxivIngestResponse(
        papers_fetched=ingestion_result.papers_fetched,
        papers_stored=ingestion_result.papers_stored,
        download_pdf=request.download_pdf,
        pdfs_downloaded=(
            _successful_download_count(papers) if request.download_pdf else 0
        ),
        pdfs_failed=_failed_download_count(papers) if request.download_pdf else 0,
        papers=papers,
    )


@router.get("/papers", response_model=PaperListResponse)
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
        papers=[_paper_response(paper, output) for paper in papers],
    )


@router.post("/papers/download-pdfs", response_model=DownloadPapersResponse)
async def download_arxiv_papers(
    request: DownloadPapersRequest,
    session: Session = Depends(get_db_session),
    storage: StorageProvider = Depends(get_s3_storage),
) -> DownloadPapersResponse:
    papers = await _download_papers(
        paper_ids=request.paper_ids,
        session=session,
        storage=storage,
    )

    return DownloadPapersResponse(
        requested=len(request.paper_ids),
        downloaded=_successful_download_count(papers),
        failed=_failed_download_count(papers),
        papers=papers,
    )


@router.get("/papers/{paper_id}", response_model=PaperDetailResponse)
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
        paper=_paper_response(paper, output),
    )


async def _download_papers(
    paper_ids: list[UUID],
    session: Session,
    storage: StorageProvider,
) -> list[PaperIngestionItem]:
    paper_repository = PaperRepository(session)
    download_service = PaperDownloadService(session=session, storage=storage)
    results: list[PaperIngestionItem] = []

    for paper_id in paper_ids:
        paper = paper_repository.get_by_id(paper_id)

        if paper is None:
            results.append(
                PaperIngestionItem(
                    paper_id=paper_id,
                    arxiv_id=None,
                    title=None,
                    authors=[],
                    categories=[],
                    published_date=None,
                    ingestion_status=None,
                    pdf_object_key=None,
                    download_error="Paper not found",
                )
            )
            continue

        try:
            pdf_object_key = await download_service.download_pdf_to_storage(paper_id)
            session.refresh(paper)

            results.append(_paper_item(paper, pdf_object_key=pdf_object_key))

        except Exception as error:
            results.append(_paper_item(paper, download_error=str(error)))

    return results


def _paper_item(
    paper: PaperModel,
    pdf_object_key: str | None = None,
    download_error: str | None = None,
) -> PaperIngestionItem:
    return PaperIngestionItem(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=paper.authors,
        categories=paper.categories,
        published_date=paper.published_date,
        ingestion_status=paper.ingestion_status,
        pdf_object_key=(
            pdf_object_key if pdf_object_key is not None else paper.pdf_object_key
        ),
        download_error=download_error,
    )


def _paper_response(
    paper: PaperModel,
    output: Literal["compact", "full"],
) -> CompactPaperResponse | FullPaperResponse:
    if output == "full":
        return FullPaperResponse(
            paper_id=paper.id,
            arxiv_id=paper.arxiv_id,
            version=paper.version,
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            categories=paper.categories,
            published_date=paper.published_date,
            pdf_url=paper.pdf_url,
            doi=paper.doi,
            pdf_object_key=paper.pdf_object_key,
            parsed_json_object_key=paper.parsed_json_object_key,
            parser_name=paper.parser_name,
            parser_error=paper.parser_error,
            ingestion_status=paper.ingestion_status,
            parser_status=paper.parser_status,
            indexing_status=paper.indexing_status,
            created_at=paper.created_at,
            updated_at=paper.updated_at,
        )

    return CompactPaperResponse(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=paper.authors,
        categories=paper.categories,
        published_date=paper.published_date,
    )


def _successful_download_count(papers: list[PaperIngestionItem]) -> int:
    return sum(
        1 for paper in papers if paper.pdf_object_key and not paper.download_error
    )


def _failed_download_count(papers: list[PaperIngestionItem]) -> int:
    return sum(1 for paper in papers if paper.download_error)
