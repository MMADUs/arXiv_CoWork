# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from rag.db.model import (
    PaperModel,
    PaperChunkingStatus,
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
        """
        Get paper by id
        """
        statement = select(PaperModel).where(PaperModel.id == paper_id)
        return self.session.scalar(statement)

    def get_by_id_for_update(self, paper_id: UUID) -> PaperModel | None:
        """
        Get paper by id and lock the row for futher updates/modification
        """
        statement = (
            select(PaperModel).where(PaperModel.id == paper_id).with_for_update()
        )
        return self.session.scalar(statement)

    def get_by_arxiv_id(self, arxiv_id: str) -> PaperModel | None:
        statement = select(PaperModel).where(PaperModel.arxiv_id == arxiv_id)
        return self.session.scalar(statement)

    def delete(self, paper: PaperModel) -> None:
        self.session.delete(paper)

    def list_recent_page(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[PaperModel], int]:
        base_statement = select(PaperModel)
        total_statement = select(func.count()).select_from(base_statement.subquery())
        page_statement = (
            base_statement.order_by(PaperModel.published_date.desc())
            .limit(limit)
            .offset(offset)
        )

        papers = list(self.session.scalars(page_statement))
        total = self.session.scalar(total_statement) or 0

        return papers, total

    def list_failed_page(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[PaperModel], int]:
        base_statement = select(PaperModel).where(
            or_(
                PaperModel.ingestion_status.in_(
                    [
                        PaperIngestionStatus.METADATA_FAILED,
                        PaperIngestionStatus.PDF_FAILED,
                    ]
                ),
                PaperModel.parser_status == PaperParserStatus.FAILED,
                PaperModel.chunking_status == PaperChunkingStatus.FAILED,
                PaperModel.indexing_status == PaperIndexingStatus.FAILED,
            )
        )
        total_statement = select(func.count()).select_from(base_statement.subquery())
        page_statement = (
            base_statement.order_by(
                PaperModel.updated_at.desc(),
                PaperModel.published_date.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        papers = list(self.session.scalars(page_statement))
        total = self.session.scalar(total_statement) or 0

        return papers, total

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
                chunking_status=PaperChunkingStatus.PENDING,
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

        # If the PDF is not stored yet, make refreshed metadata eligible for download.
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
        """
        Get all papers where indexing status is `PaperIndexingStatus.PENDING`

        this also includes papers with status `PaperParserStatus.FAILED` and `PaperChunkingStatus.FAILED`
        because they're failed on prior indexing stages

        Args:
            limit:
                the most amount of paper to be listed
            include_failed:
                include papers with status of `PaperIndexingStatus.FAILED`
        """
        statuses = [PaperIndexingStatus.PENDING]

        if include_failed:
            statuses.append(PaperIndexingStatus.FAILED)

        statement = (
            select(PaperModel)
            .where(PaperModel.pdf_object_key.is_not(None))
            .where(PaperModel.indexing_status.in_(statuses))
            .where(PaperModel.chunking_status != PaperChunkingStatus.NO_CHUNKS)
            .order_by(PaperModel.updated_at.asc(), PaperModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        if not include_failed:
            statement = statement.where(
                PaperModel.parser_status != PaperParserStatus.FAILED
            ).where(PaperModel.chunking_status != PaperChunkingStatus.FAILED)

        return list(self.session.scalars(statement))

    def mark_parse_started(self, paper: PaperModel) -> PaperModel:
        paper.parser_status = PaperParserStatus.PARSING
        paper.parser_error = None
        paper.chunking_status = PaperChunkingStatus.PENDING
        paper.chunking_error = None
        paper.indexing_status = PaperIndexingStatus.PENDING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

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
        paper.chunking_status = PaperChunkingStatus.PENDING
        paper.chunking_error = None
        paper.indexing_status = PaperIndexingStatus.PENDING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_parse_failed(self, paper: PaperModel, error: str) -> PaperModel:
        """
        mark paper status when pdf parsing failed
        """
        paper.parser_status = PaperParserStatus.FAILED
        paper.parser_error = error
        paper.chunking_status = PaperChunkingStatus.PENDING
        paper.chunking_error = None
        paper.indexing_status = PaperIndexingStatus.PENDING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_chunking_started(self, paper: PaperModel) -> PaperModel:
        paper.chunking_status = PaperChunkingStatus.CHUNKING
        paper.chunking_error = None
        paper.indexing_status = PaperIndexingStatus.PENDING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_chunked(self, paper: PaperModel) -> PaperModel:
        paper.chunking_status = PaperChunkingStatus.CHUNKED
        paper.chunking_error = None
        paper.indexing_status = PaperIndexingStatus.PENDING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_chunking_failed(self, paper: PaperModel, error: str) -> PaperModel:
        paper.chunking_status = PaperChunkingStatus.FAILED
        paper.chunking_error = error
        paper.indexing_status = PaperIndexingStatus.PENDING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_chunking_skipped(self, paper: PaperModel) -> PaperModel:
        """
        mark paper status when parsed content produced no chunks
        """
        paper.chunking_status = PaperChunkingStatus.NO_CHUNKS
        paper.chunking_error = None
        paper.indexing_status = PaperIndexingStatus.PENDING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_chunks_removed(self, paper: PaperModel) -> PaperModel:
        paper.chunking_status = PaperChunkingStatus.PENDING
        paper.chunking_error = None
        paper.indexing_status = PaperIndexingStatus.PENDING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_indexing_started(self, paper: PaperModel) -> PaperModel:
        """
        mark paper status when indexing paper chunks
        """
        paper.indexing_status = PaperIndexingStatus.INDEXING
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_indexed(self, paper: PaperModel) -> PaperModel:
        """
        mark paper status when paper chunks is successfully indexed
        """
        paper.indexing_status = PaperIndexingStatus.INDEXED
        paper.indexing_error = None
        paper.updated_at = datetime.now(timezone.utc)

        return paper

    def mark_indexing_failed(
        self,
        paper: PaperModel,
        error: str | None = None,
    ) -> PaperModel:
        """
        mark paper status when indexing chunks failed
        """
        paper.indexing_status = PaperIndexingStatus.FAILED
        if error is not None:
            paper.indexing_error = error
        paper.updated_at = datetime.now(timezone.utc)

        return paper
