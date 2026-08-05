# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from rag.db.model import (
    PaperModel,
    PaperIngestionStatus,
    PaperIndexingStatus,
    PaperParserStatus,
)
from rag.schema.arxiv_schema import ArxivPaperMetadata


class PaperRepository:
    """
    PaperRepository provides database access & operation for Paper Model
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, paper_id: UUID) -> PaperModel | None:
        statement = select(PaperModel).where(PaperModel.id == paper_id)
        return self.session.scalar(statement)

    def get_by_id_for_update(self, paper_id: UUID) -> PaperModel | None:
        statement = (
            select(PaperModel)
            .where(PaperModel.id == paper_id)
            .with_for_update()
        )
        return self.session.scalar(statement)

    def get_by_arxiv_id(self, arxiv_id: str) -> PaperModel | None:
        statement = select(PaperModel).where(PaperModel.arxiv_id == arxiv_id)
        return self.session.scalar(statement)

    def list_recent(self, limit: int = 50, offset: int = 0) -> list[PaperModel]:
        statement = (
            select(PaperModel)
            .order_by(PaperModel.published_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement))

    def upsert_from_arxiv(self, arxiv_paper: ArxivPaperMetadata) -> PaperModel:
        """
        insert paper metadata if not exist, otherwise update existing paper metadata
        """
        existing_paper = self.get_by_arxiv_id(arxiv_paper.arxiv_id)

        # insert if does not exist
        if existing_paper is None:
            paper = PaperModel(
                arxiv_id=arxiv_paper.arxiv_id,
                version=arxiv_paper.version,
                title=arxiv_paper.title,
                authors=arxiv_paper.authors,
                abstract=arxiv_paper.abstract,
                categories=arxiv_paper.categories,
                published_date=arxiv_paper.published_date,
                # needs a fallback instead of None, we need it for pdf download
                pdf_url=arxiv_paper.pdf_url
                or self._fallback_pdf_url(arxiv_paper.arxiv_id),
                doi=arxiv_paper.doi,
                # mark ingestion as metadata fetched
                ingestion_status=PaperIngestionStatus.METADATA_FETCHED,
                # stay pending
                parser_status=PaperParserStatus.PENDING,
                indexing_status=PaperIndexingStatus.PENDING,
            )
            self.session.add(paper)
            return paper

        # update if already exist
        existing_paper.version = arxiv_paper.version
        existing_paper.title = arxiv_paper.title
        existing_paper.authors = arxiv_paper.authors
        existing_paper.abstract = arxiv_paper.abstract
        existing_paper.categories = arxiv_paper.categories
        existing_paper.published_date = arxiv_paper.published_date
        existing_paper.pdf_url = arxiv_paper.pdf_url or self._fallback_pdf_url(
            arxiv_paper.arxiv_id
        )
        existing_paper.doi = arxiv_paper.doi

        if existing_paper.pdf_object_key is None:
            existing_paper.ingestion_status = PaperIngestionStatus.METADATA_FETCHED

        existing_paper.updated_at = datetime.now(timezone.utc)

        return existing_paper

    def upsert_many_from_arxiv(
        self, papers: Iterable[ArxivPaperMetadata]
    ) -> list[PaperModel]:
        return [self.upsert_from_arxiv(paper) for paper in papers]

    def _fallback_pdf_url(self, arxiv_id: str) -> str:
        # arxiv_id is always cleaned from version, see: `ArxivClient` class
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    def mark_pdf_stored(self, paper: PaperModel, pdf_object_key: str) -> PaperModel:
        """
        mark paper status when pdf is stored successfully into object storage
        """
        paper.pdf_object_key = pdf_object_key
        paper.ingestion_status = PaperIngestionStatus.PDF_STORED
        paper.pdf_download_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_pdf_download_started(self, paper: PaperModel) -> PaperModel:
        paper.ingestion_status = PaperIngestionStatus.PDF_DOWNLOADING
        paper.pdf_download_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_pdf_download_failed(
        self,
        paper: PaperModel,
        error: str,
    ) -> PaperModel:
        paper.ingestion_status = PaperIngestionStatus.PDF_FAILED
        paper.pdf_download_error = error
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def list_pending_pdf_downloads(
        self,
        limit: int = 50,
        include_failed: bool = False,
    ) -> list[PaperModel]:
        statuses = [PaperIngestionStatus.METADATA_FETCHED]

        if include_failed:
            statuses.append(PaperIngestionStatus.PDF_FAILED)

        statement = (
            select(PaperModel)
            .where(PaperModel.pdf_object_key.is_(None))
            .where(PaperModel.ingestion_status.in_(statuses))
            .order_by(PaperModel.updated_at.asc(), PaperModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        return list(self.session.scalars(statement))

    def list_pending_indexing_papers(
        self,
        limit: int = 50,
        include_failed: bool = False,
    ) -> list[PaperModel]:
        statuses = [
            PaperIndexingStatus.PENDING,
            PaperIndexingStatus.CHUNKED,
        ]

        if include_failed:
            statuses.append(PaperIndexingStatus.FAILED)

        statement = (
            select(PaperModel)
            .where(PaperModel.pdf_object_key.is_not(None))
            .where(PaperModel.indexing_status.in_(statuses))
            .order_by(PaperModel.updated_at.asc(), PaperModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        return list(self.session.scalars(statement))

    def mark_parsed(
        self,
        paper: PaperModel,
        parsed_json_object_key: str,
        parser_name: str,
    ) -> PaperModel:
        """
        mark paper status when pdf is parsed successfully into json
        the parsed data is stored into object storage
        """
        paper.parsed_json_object_key = parsed_json_object_key
        paper.parser_name = parser_name
        paper.parser_status = PaperParserStatus.PARSED
        paper.parser_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_parse_failed(self, paper: PaperModel, error: str) -> PaperModel:
        """
        mark paper status when pdf parsing failed
        """
        paper.parser_status = PaperParserStatus.FAILED
        paper.parser_error = error
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_chunked(self, paper: PaperModel) -> PaperModel:
        """
        mark paper status when paper content is chunked
        """
        paper.indexing_status = PaperIndexingStatus.CHUNKED
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_indexing_started(self, paper: PaperModel) -> PaperModel:
        """
        mark paper status when indexing paper chunks
        """
        paper.indexing_status = PaperIndexingStatus.INDEXING
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_indexed(self, paper: PaperModel) -> PaperModel:
        """
        mark paper status when paper chunks is successfully indexed
        """
        paper.indexing_status = PaperIndexingStatus.INDEXED
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_indexing_failed(self, paper: PaperModel) -> PaperModel:
        """
        mark paper status when indexing chunks failed
        """
        paper.indexing_status = PaperIndexingStatus.FAILED
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_indexing_skipped(self, paper: PaperModel) -> PaperModel:
        """
        this is edge case, mark paper status when there is no chunk to index
        """
        paper.indexing_status = PaperIndexingStatus.NO_CHUNKS
        paper.updated_at = datetime.now(timezone.utc)

        return paper
