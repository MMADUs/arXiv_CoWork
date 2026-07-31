# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from sqlalchemy.orm import Session

from rag.db.model import PaperModel
from rag.db.repository import PaperRepository
from rag.service.arxiv import PaperDownloadService
from rag.service.storage.interface import StorageProvider
from server.routes.ingestion.schema import PaperIngestionItem


async def download_papers(
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

            results.append(paper_ingestion_item(paper, pdf_object_key=pdf_object_key))

        except Exception as error:
            results.append(paper_ingestion_item(paper, download_error=str(error)))

    return results


def paper_ingestion_item(
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


def successful_download_count(papers: list[PaperIngestionItem]) -> int:
    return sum(
        1 for paper in papers if paper.pdf_object_key and not paper.download_error
    )


def failed_download_count(papers: list[PaperIngestionItem]) -> int:
    return sum(1 for paper in papers if paper.download_error)
