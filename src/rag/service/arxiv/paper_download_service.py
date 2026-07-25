# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from uuid import UUID
from tempfile import TemporaryDirectory
from pathlib import Path

from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.repository import PaperRepository
from rag.service.storage import StorageProvider
from rag.service.arxiv.pdf_downloader import PDFDownloader
from rag.service.arxiv.utils import make_arxiv_id_safe

logger = logging.getLogger(__name__)


class PaperDownloadService:
    """
    `PaperDownloadService` downloads the paper pdf and store them into storage,
    through the `download_pdf_to_storage()` method.
    """

    def __init__(self, session: Session, storage: StorageProvider) -> None:
        self.settings = get_settings()
        self.session = session
        self.paper_repository = PaperRepository(session)
        self.pdf_downloader = PDFDownloader(self.settings.arxiv_settings)
        self.storage = storage

    async def download_pdf_to_storage(self, paper_id: UUID) -> str:
        try:
            paper = self.paper_repository.get_by_id(paper_id)

            if paper is None:
                logger.warning(
                    "Paper not found for PDF download: paper_id=%s", paper_id
                )
                raise ValueError(f"Paper not found: {paper_id}")

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

                object_key = f"arxiv/{safe_arxiv_id}/original.pdf"

                logger.info(
                    "Uploading paper PDF to storage: paper_id=%s object_key=%s",
                    paper.id,
                    object_key,
                )

                self.storage.upload_file(local_path, object_key)

            self.paper_repository.mark_pdf_stored(paper, pdf_object_key=object_key)
            self.session.commit()

            logger.info(
                "Finished paper PDF download: paper_id=%s object_key=%s",
                paper.id,
                object_key,
            )

            return object_key

        except ValueError:
            raise

        except Exception as error:
            self.session.rollback()
            logger.exception("Failed paper PDF download")
            raise RuntimeError("Failed paper PDF download") from error
