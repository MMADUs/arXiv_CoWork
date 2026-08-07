# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.repository import PaperRepository, ChunkRepository
from rag.service.storage import StorageProvider
from rag.service.chunker.text_chunker import TextChunker
from rag.schema.document_schema import ParsedDocument

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

    def chunk_parsed_paper(self, paper_id: UUID) -> dict[str, int | str]:
        try:
            paper = self.paper_repository.get_by_id(paper_id)

            if paper is None:
                raise ValueError(f"Paper with id {paper_id} not found")

            if paper.parsed_json_object_key is None:
                raise ValueError(f"Paper with id {paper_id} has no parsed JSON artifact")

            self.paper_repository.mark_chunking_started(paper)
            self.session.commit()

            parsed_json = self.storage.download_json(paper.parsed_json_object_key)
            parsed_document = ParsedDocument.model_validate(parsed_json)

            candidates = self.chunker.chunk_document(
                title=paper.title,
                abstract=paper.abstract,
                parsed_document=parsed_document,
            )

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

            total_words = sum(c.word_count for c in chunks)
            average_words = int(total_words / len(chunks)) if chunks else 0

            return {
                "paper_id": str(paper.id),
                "arxiv_id": paper.arxiv_id,
                "chunks_created": len(chunks),
                "average_chunk_words": average_words,
            }

        except ValueError:
            raise

        except Exception as error:
            self.session.rollback()
            logger.exception("Failed parsed paper chunking")
            raise RuntimeError(_chunking_error_message(error)) from error


def _chunking_error_message(error: Exception) -> str:
    message = str(error).splitlines()[0]

    if "NUL (0x00)" in str(error):
        message = "PostgreSQL text fields cannot contain NUL (0x00) bytes"

    return f"Failed parsed paper chunking: {message}"
