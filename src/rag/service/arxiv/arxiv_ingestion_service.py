# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.repository import PaperRepository
from rag.schema.arxiv_schema import ArxivQueryParams
from rag.service.arxiv.arxiv_client import ArxivClient
from rag.service.arxiv.arxiv_exceptions import ArxivPersistenceError, ArxivServiceError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestedPaperResult:
    paper_id: UUID
    arxiv_id: str
    title: str
    authors: list[str]
    categories: list[str]
    published_date: datetime


@dataclass(slots=True)
class ArxivIngestionResult:
    papers_fetched: int
    papers_stored: int
    papers: list[IngestedPaperResult]


class ArxivIngestionService:
    """
    `ArxivIngestionService` fetches paper metadata and store them into database,
    through `ingest_metadata()` method.
    """

    def __init__(
        self,
        session: Session,
        arxiv_client: ArxivClient | None = None,
    ) -> None:
        self.settings = get_settings()
        self.session = session
        self.arxiv_client = arxiv_client or ArxivClient(self.settings.arxiv_settings)
        self.paper_repository = PaperRepository(session)

    async def ingest_metadata(self, query: ArxivQueryParams) -> ArxivIngestionResult:
        """ 
        Raises:
            ArxivMetadataFetchError: 
                if arxiv api request fails after retries
            ArxivMetadataParseError: 
                if arxiv xml response cannot be parsed
            ArxivPersistenceError: 
                if database error when processing arxiv data (sqlalchemy)
        """
        try:
            papers_metadata = await self.arxiv_client.fetch_papers(query)

            logger.info("Storing arXiv metadata: count=%d", len(papers_metadata))

            if not papers_metadata:
                return ArxivIngestionResult(
                    papers_fetched=0,
                    papers_stored=0,
                    papers=[],
                )

            stored_papers = self.paper_repository.upsert_many_from_arxiv(
                papers=papers_metadata
            )
            self.session.flush()
            self.session.commit()

            return ArxivIngestionResult(
                papers_fetched=len(papers_metadata),
                papers_stored=len(stored_papers),
                papers=[
                    IngestedPaperResult(
                        paper_id=paper.id,
                        arxiv_id=paper.arxiv_id,
                        title=paper.title,
                        authors=paper.authors,
                        categories=paper.categories,
                        published_date=paper.published_date,
                    )
                    for paper in stored_papers
                ],
            )

        except ArxivServiceError:
            self.session.rollback()
            raise

        except SQLAlchemyError as error:
            self.session.rollback()
            logger.exception("Failed arXiv metadata ingestion")
            raise ArxivPersistenceError("Failed to persist arXiv metadata") from error
