# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.repository import ChunkRepository, PaperRepository
from rag.schema.document_schema import ParsedDocument
from rag.service.chunker.chunker_exceptions import (
    ChunkerExecutionError,
    ChunkerPaperNotFoundError,
    ChunkerParsedDocumentNotFoundError,
    ChunkerParsedDocumentValidationError,
    ChunkerPersistenceError,
    ChunkerServiceError,
    ChunkerStorageError,
)
from rag.service.chunker.text_chunker import TextChunker
from rag.service.storage import (
    StorageDownloadError,
    StorageJsonError,
    StorageProvider,
)

logger = logging.getLogger(__name__)


class PaperChunkingService:
    """
    `PaperChunkingService` chunks parsed pdf text from storage,
    and stored every chunks into database

    the process is done through the `chunk_parsed_paper()` method.
    """

    def __init__(self, session: Session, storage: StorageProvider) -> None:
        self.settings = get_settings()
        self.session = session
        self.paper_repository = PaperRepository(session)
        self.chunk_repository = ChunkRepository(session)
        self.storage = storage
        self.chunker = TextChunker(self.settings.chunker_settings)

    def chunk_parsed_paper(self, paper_id: UUID) -> int:
        """
        Returns:
            number of chunks created from paper id

        Raises:
            ChunkerPaperNotFoundError:
                if paper does not exist locally
            ChunkerParsedDocumentNotFoundError:
                if paper has no parsed JSON artifact
            ChunkerParsedDocumentValidationError:
                if parsed document is invalid
            ChunkerStorageError:
                if parsed document download fails
            ChunkerExecutionError:
                if text chunking fails
            ChunkerPersistenceError:
                if local chunking state persistence fails
        """
        try:
            paper = self.paper_repository.get_by_id(paper_id)

            if paper is None:
                raise ChunkerPaperNotFoundError(f"Paper with id {paper_id} not found")

            if paper.parsed_json_object_key is None:
                raise ChunkerParsedDocumentNotFoundError(
                    f"Paper with id {paper_id} has no parsed JSON artifact"
                )

            self.paper_repository.mark_chunking_started(paper)
            self.session.commit()

            try:
                parsed_json = self.storage.download_json(paper.parsed_json_object_key)

            except StorageJsonError as error:
                raise ChunkerParsedDocumentValidationError(
                    "Failed to load parsed paper JSON artifact: "
                    f"{paper.parsed_json_object_key}"
                ) from error

            except StorageDownloadError as error:
                raise ChunkerStorageError(
                    "Failed to download parsed paper JSON artifact: "
                    f"{paper.parsed_json_object_key}"
                ) from error

            try:
                parsed_document = ParsedDocument.model_validate(parsed_json)

            except ValidationError as error:
                raise ChunkerParsedDocumentValidationError(
                    "Parsed paper JSON artifact is invalid: "
                    f"{paper.parsed_json_object_key}"
                ) from error

            try:
                candidates = self.chunker.chunk_document(
                    title=paper.title,
                    abstract=paper.abstract,
                    parsed_document=parsed_document,
                )

            # NOTE: broad exception can catch tiny error that are not captured by custom exceptions
            # since `.chunk_document()` itself does not throw any custom exceptions
            except Exception as error:
                raise ChunkerExecutionError(
                    "TextChunker failed to chunk a parsed paper"
                ) from error

            chunks = self.chunk_repository.replace_paper_chunks(
                paper=paper,
                candidates=candidates,
                source_object_key=paper.parsed_json_object_key,
            )

            if not chunks:
                self.paper_repository.mark_chunking_skipped(paper)
            else:
                self.paper_repository.mark_chunked(paper)

            self.session.commit()

            return len(chunks)

        except ChunkerServiceError:
            self.session.rollback()
            raise

        except SQLAlchemyError as error:
            self.session.rollback()
            logger.exception("Failed parsed paper chunking")
            raise ChunkerPersistenceError(
                "Failed to persist paper chunking state"
            ) from error
