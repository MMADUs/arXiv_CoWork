# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.repository import PaperRepository
from rag.service.arxiv.exceptions import (
    ArxivPaperNotFoundError,
    ArxivPersistenceError,
    ArxivServiceError,
    ArxivStorageError,
)
from rag.service.arxiv.pdf_downloader import PDFDownloader
from rag.service.arxiv.utils import make_arxiv_id_safe
from rag.service.storage import StorageProvider, StorageServiceError

logger = logging.getLogger(__name__)


class PaperDownloadService:
    """
    `PaperDownloadService` downloads the paper pdf and store them into storage,
    through the `download_pdf_to_storage()` method.
    """

    def __init__(
        self,
        session: Session,
        storage: StorageProvider,
        pdf_downloader: PDFDownloader | None = None,
    ) -> None:
        self.settings = get_settings()
        self.session = session
        self.paper_repository = PaperRepository(session)
        self.pdf_downloader = pdf_downloader or PDFDownloader(
            self.settings.arxiv_settings
        )
        self.storage = storage

    async def download_pdf_to_storage(self, paper_id: UUID) -> str:
        """
        Returns:
            stored pdf object key from storage provider

        Raises:
            ArxivInvalidPdfUrlError: 
                if arxiv pdf url is invalid
            ArxivInvalidDownloadedPdfError: 
                if downloaded pdf is in incorrect format
            ArxivPdfDownloadError: 
                if pdf failed to download after retries
            ArxivPaperNotFoundError: 
                if paper not found by id
            ArxivStorageError: 
                if storage error when processing arxiv artifacts (object storage)
            ArxivPersistenceError: 
                if database error when processing arxiv data (sqlalchemy)
        """
        try:
            paper = self.paper_repository.get_by_id(paper_id)

            if paper is None:
                logger.warning(
                    "Paper not found for PDF download: paper_id=%s", paper_id
                )
                raise ArxivPaperNotFoundError(f"Paper not found: {paper_id}")

            logger.info(
                "Downloading paper PDF: paper_id=%s arxiv_id=%s pdf_url=%s",
                paper.id,
                paper.arxiv_id,
                paper.pdf_url,
            )

            with TemporaryDirectory() as temp_dir:
                safe_arxiv_id = make_arxiv_id_safe(paper.arxiv_id)

                local_path = Path(temp_dir) / f"{safe_arxiv_id}.pdf"

                await self.pdf_downloader.download_pdf(
                    pdf_url=paper.pdf_url,
                    output_path=local_path,
                )

                # NOTE: object key must be consistent/unchange across software updates
                object_key = f"arxiv/{safe_arxiv_id}/original.pdf"

                try:
                    self.storage.upload_file(local_path, object_key)

                except StorageServiceError as error:
                    raise ArxivStorageError(
                        f"Failed to upload paper PDF to storage: {object_key}"
                    ) from error

            self.paper_repository.mark_pdf_stored(paper, pdf_object_key=object_key)
            self.session.commit()

            logger.info(
                "Finished paper PDF download: paper_id=%s object_key=%s",
                paper.id,
                object_key,
            )

            return object_key

        except ArxivServiceError:
            self.session.rollback()
            raise

        except SQLAlchemyError as error:
            self.session.rollback()
            logger.exception("Failed paper PDF download")
            raise ArxivPersistenceError("Failed to persist paper PDF state") from error
