# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from sqlalchemy.orm import Session

from rag.db.model import PaperIngestionStatus, PaperModel
from rag.db.repository import PaperRepository
from server.routes.ingestion.ingestion_schema import DownloadPaperItem, PaperIngestionItem
from worker.queue_schema import PdfDownloadQueue
from worker.workflow import enqueue_paper_pdf_download


def enqueue_pdf_download_by_id(
    paper_id: UUID,
    session: Session,
    force_download: bool = False,
) -> DownloadPaperItem | None:
    paper_repository = PaperRepository(session)
    paper = paper_repository.get_by_id_for_update(paper_id)

    if paper is None:
        return None

    return _enqueue_pdf_download_for_paper(
        paper=paper,
        paper_repository=paper_repository,
        session=session,
        force_download=force_download,
    )


def enqueue_pending_pdf_downloads(
    session: Session,
    limit: int,
    include_failed: bool = False,
) -> list[DownloadPaperItem]:
    paper_repository = PaperRepository(session)
    papers = paper_repository.list_pending_pdf_downloads(
        limit=limit,
        include_failed=include_failed,
    )

    return [
        _enqueue_pdf_download_for_paper(
            paper=paper,
            paper_repository=paper_repository,
            session=session,
            force_download=False,
        )
        for paper in papers
    ]


def enqueue_ingested_pdf_downloads(
    paper_ids: list[UUID],
    session: Session,
) -> list[PaperIngestionItem]:
    paper_repository = PaperRepository(session)
    results: list[PaperIngestionItem] = []

    for paper_id in paper_ids:
        paper = paper_repository.get_by_id_for_update(paper_id)

        if paper is None:
            results.append(
                PaperIngestionItem(
                    paper_id=paper_id,
                    arxiv_id=None,
                    title=None,
                    authors=[],
                    categories=[],
                    published_date=None,
                )
            )
            continue

        download_item = _enqueue_pdf_download_for_paper(
            paper=paper,
            paper_repository=paper_repository,
            session=session,
            force_download=False,
        )

        results.append(
            _paper_ingestion_item(
                paper=paper,
                pdf_download_task_id=download_item.task_id,
                pdf_download_status=download_item.pdf_download_status,
            )
        )

    return results


def _paper_ingestion_item(
    paper: PaperModel,
    pdf_download_task_id: str | None = None,
    pdf_download_status: str | None = None,
) -> PaperIngestionItem:
    return PaperIngestionItem(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=paper.authors,
        categories=paper.categories,
        published_date=paper.published_date,
        pdf_download_task_id=pdf_download_task_id,
        pdf_download_status=pdf_download_status,
    )


# declare as variable instead for consistency reason
SUCCESSFUL_QUEUE = "download_in_queue"


def _enqueue_pdf_download_for_paper(
    paper: PaperModel,
    paper_repository: PaperRepository,
    session: Session,
    force_download: bool,
) -> DownloadPaperItem:
    if paper.pdf_object_key and not force_download:
        return _download_item(
            paper=paper,
            task_id=None,
            pdf_download_status=PaperIngestionStatus.PDF_STORED,
        )

    if paper.ingestion_status == PaperIngestionStatus.PDF_DOWNLOADING:
        return _download_item(
            paper=paper,
            task_id=None,
            pdf_download_status=PaperIngestionStatus.PDF_DOWNLOADING,
        )

    paper_repository.mark_pdf_download_started(paper)
    session.commit()

    try:
        task_id = enqueue_paper_pdf_download(
            PdfDownloadQueue(
                paper_id=paper.id,
                force_download=force_download,
            )
        )

    except Exception:
        paper_repository.mark_pdf_download_failed(
            paper,
            "Failed to enqueue PDF download task",
        )
        session.commit()
        raise

    return _download_item(
        paper=paper,
        task_id=task_id,
        pdf_download_status=SUCCESSFUL_QUEUE,
    )


def _download_item(
    paper: PaperModel,
    task_id: str | None,
    pdf_download_status: str,
) -> DownloadPaperItem:
    return DownloadPaperItem(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        task_id=task_id,
        pdf_download_status=pdf_download_status,
    )


def queued_download_count(
    papers: (
        list[PaperIngestionItem] | list[DownloadPaperItem]
    ),  # both type should at least have the attribute `pdf_download_status` (error prone)
) -> int:
    return sum(1 for paper in papers if paper.pdf_download_status == SUCCESSFUL_QUEUE)


def skipped_download_count(
    papers: (
        list[PaperIngestionItem] | list[DownloadPaperItem]
    ),  # both type should at least have the attribute `pdf_download_status` (error prone)
) -> int:
    return sum(
        1
        for paper in papers
        if paper.pdf_download_status
        in {PaperIngestionStatus.PDF_STORED, PaperIngestionStatus.PDF_DOWNLOADING}
    )
