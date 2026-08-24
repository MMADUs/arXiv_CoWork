# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.model import PaperModel
from rag.db.repository import PaperRepository
from rag.schema.document_schema import ParsedDocument, ParsedSection
from rag.service.arxiv import make_arxiv_id_safe
from rag.service.parser.parser_exceptions import (
    ParserPaperNotFoundError,
    ParserPdfNotStoredError,
    ParserPersistenceError,
    ParserServiceError,
    ParserStorageError,
)
from rag.service.parser.parser_provider import ParserProvider
from rag.service.storage import StorageProvider, StorageServiceError

logger = logging.getLogger(__name__)


class PaperParsingService:
    """
    `PaperParsingService` parse stored pdf in storage to text,
    the parsed text is stored into storage as well

    the process is done through the `parse_stored_pdf()` method.
    """

    def __init__(
        self,
        session: Session,
        storage: StorageProvider,
        parser_provider: ParserProvider | None = None,
    ) -> None:
        self.settings = get_settings()
        self.session = session
        self.paper_repository = PaperRepository(session)
        self.storage = storage
        self.parser_provider = parser_provider or ParserProvider(
            self.settings.parser_settings
        )

    def parse_stored_pdf(self, paper_id: UUID) -> str:
        """
        Returns:
            name of the parser that produced the parsed document

        Raises:
            ParserPaperNotFoundError: 
                if the paper does not exist locally.
            ParserPdfNotStoredError: 
                if the paper has no stored PDF object key.
            ParserPdfValidationError: 
                if the downloaded PDF fails parser validation.
            ParserExecutionError: 
                if PDF parsing fails.
            ParserStorageError: 
                if downloading the PDF or uploading parsed JSON fails.
            ParserPersistenceError: 
                if local parsing state persistence fails.
        """
        paper = None
        parsing_started = False

        try:
            paper = self.paper_repository.get_by_id(paper_id)

            logger.info(
                "Parsing stored paper PDF: paper_id=%s arxiv_id=%s",
                paper.id,
                paper.arxiv_id,
            )

            if paper is None:
                logger.warning("Paper not found for PDF parsing: paper_id=%s", paper_id)
                raise ParserPaperNotFoundError(f"Paper with id {paper_id} not found")

            if paper.pdf_object_key is None:
                logger.warning("Paper has no stored PDF: paper_id=%s", paper_id)
                raise ParserPdfNotStoredError(
                    f"Paper with id {paper_id} has no stored PDF"
                )

            safe_arxiv_id = make_arxiv_id_safe(paper.arxiv_id)

            self.paper_repository.mark_parse_started(paper)
            self.session.commit()
            parsing_started = True

            with TemporaryDirectory() as temp_dir:
                local_path = Path(temp_dir) / "original.pdf"

                try:
                    self.storage.download_file(
                        object_key=paper.pdf_object_key,
                        local_path=local_path,
                    )

                except StorageServiceError as error:
                    raise ParserStorageError(
                        "Failed to download paper PDF from storage: "
                        f"{paper.pdf_object_key}"
                    ) from error

                parsed = self.parser_provider.parse_pdf(local_path)
                parsed = _sanitize_parsed_document(parsed)

                json_object_key = f"arxiv/{safe_arxiv_id}/parsed/parsed_document.json"

                try:
                    self.storage.upload_json(parsed.model_dump(), json_object_key)

                except StorageServiceError as error:
                    raise ParserStorageError(
                        "Failed to upload parsed paper JSON to storage: "
                        f"{json_object_key}"
                    ) from error

            self.paper_repository.mark_parsed(
                paper=paper,
                parsed_json_object_key=json_object_key,
                parser_name=parsed.parser_name,
            )
            self.session.commit()

            return parsed.parser_name

        except ParserServiceError as error:
            if paper is not None and parsing_started:
                self._mark_parse_failed(paper, str(error))

            raise

        except SQLAlchemyError as error:
            self.session.rollback()
            logger.exception("Failed paper PDF parsing")
            raise ParserPersistenceError(
                "Failed to persist paper parsing state"
            ) from error

    def _mark_parse_failed(self, paper: PaperModel, error: str) -> None:
        try:
            self.paper_repository.mark_parse_failed(paper, error)
            self.session.commit()

        except SQLAlchemyError as mark_error:
            self.session.rollback()
            raise ParserPersistenceError(
                "Failed to persist paper parsing failure state"
            ) from mark_error


def _sanitize_parsed_document(parsed: ParsedDocument) -> ParsedDocument:
    return parsed.model_copy(
        update={
            "raw_text": _sanitize_text(parsed.raw_text),
            "sections": [
                ParsedSection(
                    title=_sanitize_text(section.title),
                    content=_sanitize_text(section.content),
                    header_level=section.header_level,
                )
                for section in parsed.sections
            ],
            "metadata": {
                key: _sanitize_text(value) if isinstance(value, str) else value
                for key, value in parsed.metadata.items()
            },
        }
    )


def _sanitize_text(text: str) -> str:
    return text.replace("\x00", "")
