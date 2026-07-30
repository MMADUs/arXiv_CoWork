# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.repository import PaperRepository
from rag.schema.arxiv_schema import ArxivQueryParams
from rag.service.arxiv.arxiv_client import ArxivClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestedPaperResult:
    paper_id: UUID
    arxiv_id: str
    title: str
    authors: list[str]
    categories: list[str]
    published_date: datetime
    ingestion_status: str
    pdf_object_key: str | None


@dataclass(slots=True)
class ArxivIngestionResult:
    query: ArxivQueryParams
    papers_fetched: int
    papers_stored: int
    arxiv_ids: list[str]
    papers: list[IngestedPaperResult]


class ArxivIngestionService:
    """
    `ArxivIngestionService` fetches paper metadata and store them into database,
    through `ingest_metadata()` method.
    """

    def __init__(self, session: Session) -> None:
        self.settings = get_settings()
        self.session = session
        self.arxiv_client = ArxivClient(self.settings.arxiv_settings)
        self.paper_repository = PaperRepository(session)

    async def ingest_metadata(self, query: ArxivQueryParams) -> ArxivIngestionResult:
        try:
            logger.info("Starting arXiv client metadata ingestion")

            papers_metadata = await self.arxiv_client.fetch_papers(query)

            if not papers_metadata:
                logger.info("No arXiv papers matched query: %s", query.model_dump())

                return ArxivIngestionResult(
                    query=query,
                    papers_fetched=0,
                    papers_stored=0,
                    arxiv_ids=[],
                    papers=[],
                )

            logger.info("Storing arXiv metadata: count=%d", len(papers_metadata))

            stored_papers = self.paper_repository.upsert_many_from_arxiv(
                papers=papers_metadata
            )
            self.session.flush()
            self.session.commit()

            logger.info(
                "Finished arXiv metadata ingestion: stored=%d", len(stored_papers)
            )

            return ArxivIngestionResult(
                query=query,
                papers_fetched=len(papers_metadata),
                papers_stored=len(stored_papers),
                arxiv_ids=[p.arxiv_id for p in papers_metadata],
                papers=[
                    IngestedPaperResult(
                        paper_id=paper.id,
                        arxiv_id=paper.arxiv_id,
                        title=paper.title,
                        authors=paper.authors,
                        categories=paper.categories,
                        published_date=paper.published_date,
                        ingestion_status=paper.ingestion_status,
                        pdf_object_key=paper.pdf_object_key,
                    )
                    for paper in stored_papers
                ],
            )

        except Exception as error:
            self.session.rollback()
            logger.exception("Failed arXiv metadata ingestion")
            raise RuntimeError("Failed arXiv metadata ingestion") from error
