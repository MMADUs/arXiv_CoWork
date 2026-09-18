# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from rag.db.repository import PaperRepository
from rag.service.arxiv import (
    ArxivClient,
    ArxivIngestionService,
    ArxivNonRetryableError,
    ArxivRetryableError,
    ArxivServiceError,
)
from rag.service.arxiv.smart_search import (
    SmartSearchNodes,
    build_smart_search_graph,
)
from rag.service.llm.llm_interface import LLMProvider
from server.dependencies import get_arxiv_client, get_db_session, get_llm_provider
from server.routes.ingestion.ingestion_helpers import (
    enqueue_pdf_download_by_id,
    enqueue_ingested_pdf_downloads,
    enqueue_pending_pdf_downloads,
    queued_download_count,
    skipped_download_count,
    SUCCESSFUL_QUEUE,
)
from server.routes.ingestion.ingestion_schema import (
    ArxivIngestResponse,
    ArxivQueryPlanRequest,
    ArxivQueryPlanResponse,
    ArxivSearchPaperItem,
    ArxivSearchRequest,
    ArxivSearchResponse,
    DownloadPaperRequest,
    DownloadPaperResponse,
    DownloadPendingPapersRequest,
    PaperIngestionRequest,
    PaperIngestionItem,
    SelectedPapersIngestionRequest,
    SelectedPapersIngestionResponse,
)

router = APIRouter(prefix="/papers", tags=["paper-ingestion"])


@router.post("/arxiv-query-plan", response_model=ArxivQueryPlanResponse)
async def plan_arxiv_query_route(
    request: ArxivQueryPlanRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> ArxivQueryPlanResponse:
    nodes = SmartSearchNodes(llm_provider=llm_provider)
    graph = build_smart_search_graph(nodes)

    try:
        state = await graph.ainvoke({"user_query": request.prompt})

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to plan arXiv query: {error}",
        ) from error

    return _smart_search_plan_response(state)


@router.post("/arxiv-query-plan/stream")
async def stream_arxiv_query_plan_route(
    request: ArxivQueryPlanRequest,
    connection: Request,
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        status_queue: asyncio.Queue[str] = asyncio.Queue()
        nodes = SmartSearchNodes(llm_provider=llm_provider)
        graph = build_smart_search_graph(nodes)

        async def emit_status(text: str) -> None:
            await status_queue.put(text)

        nodes.status_callback = emit_status
        task = asyncio.create_task(graph.ainvoke({"user_query": request.prompt}))

        try:
            while not task.done():
                if await connection.is_disconnected():
                    task.cancel()
                    raise asyncio.CancelledError

                try:
                    status_text = await asyncio.wait_for(
                        status_queue.get(),
                        timeout=0.25,
                    )
                    yield _smart_search_sse_event(
                        "smart_search.status",
                        {"text": status_text},
                    )
                except asyncio.TimeoutError:
                    continue

            while not status_queue.empty():
                yield _smart_search_sse_event(
                    "smart_search.status",
                    {"text": status_queue.get_nowait()},
                )

            state = await task
            response = _smart_search_plan_response(state)
            yield _smart_search_sse_event(
                "smart_search.completed",
                response.model_dump(mode="json"),
            )

        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise

        except HTTPException as error:
            yield _smart_search_sse_event(
                "smart_search.error",
                {"message": str(error.detail)},
            )

        except Exception as error:
            yield _smart_search_sse_event(
                "smart_search.error",
                {"message": f"Failed to plan arXiv query: {error}"},
            )

        finally:
            nodes.status_callback = None

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _smart_search_plan_response(state: dict) -> ArxivQueryPlanResponse:
    if state.get("blocked"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=state.get("response") or state.get("summary") or "Request blocked.",
        )

    if not state.get("plan"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=state.get("summary") or "Failed to plan arXiv query.",
        )

    plan = state["plan"]

    return ArxivQueryPlanResponse(
        keywords=plan.get("all_terms"),
        title=plan.get("title_terms"),
        abstract=plan.get("abstract_terms"),
        authors=plan.get("authors"),
        categories=plan.get("categories"),
        exclude_categories=plan.get("exclude_categories"),
        submitted_from=plan.get("submitted_from"),
        submitted_to=plan.get("submitted_to"),
        max_results=plan["max_results"],
        sort_by=plan["sort_by"],
        sort_order=plan["sort_order"],
        explanation=plan.get("explanation", ""),
    )


def _smart_search_sse_event(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/arxiv-search", response_model=ArxivSearchResponse)
async def search_arxiv_route(
    request: ArxivSearchRequest,
    session: Session = Depends(get_db_session),
    arxiv_client: ArxivClient = Depends(get_arxiv_client),
) -> ArxivSearchResponse:
    try:
        query_params = request.to_arxiv_query_params()

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    try:
        papers = await arxiv_client.fetch_papers(query_params)

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

    paper_repository = PaperRepository(session)
    items: list[ArxivSearchPaperItem] = []

    for paper in papers:
        existing = paper_repository.get_by_arxiv_id(paper.arxiv_id)
        items.append(
            ArxivSearchPaperItem(
                **paper.model_dump(),
                already_exists=existing is not None,
                existing_paper_id=existing.id if existing else None,
            )
        )

    return ArxivSearchResponse(
        count=len(items),
        papers=items,
    )


@router.post(
    "/ingest-selected",
    response_model=SelectedPapersIngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_selected_papers_route(
    request: SelectedPapersIngestionRequest,
    session: Session = Depends(get_db_session),
) -> SelectedPapersIngestionResponse:
    paper_repository = PaperRepository(session)
    existing_arxiv_ids = {
        paper.arxiv_id
        for item in request.papers
        if (paper := paper_repository.get_by_arxiv_id(item.arxiv_id)) is not None
    }

    try:
        stored_papers = paper_repository.upsert_many_from_arxiv(request.papers)
        session.flush()
        session.commit()

    except Exception as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to store selected papers: {error}",
        ) from error

    stored_items = [
        PaperIngestionItem(
            paper_id=paper.id,
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            authors=paper.authors,
            categories=paper.categories,
            published_date=paper.published_date,
        )
        for paper in stored_papers
    ]

    try:
        papers_with_downloads = enqueue_ingested_pdf_downloads(
            paper_ids=[paper.paper_id for paper in stored_items],
            session=session,
        )

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to enqueue PDF downloads: {error}",
        ) from error

    created = sum(
        1 for paper in stored_papers if paper.arxiv_id not in existing_arxiv_ids
    )
    updated = len(stored_papers) - created

    return SelectedPapersIngestionResponse(
        requested=len(request.papers),
        created=created,
        updated=updated,
        pdf_downloads_queued=queued_download_count(papers_with_downloads),
        pdf_downloads_skipped=skipped_download_count(papers_with_downloads),
        papers=papers_with_downloads,
    )


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
