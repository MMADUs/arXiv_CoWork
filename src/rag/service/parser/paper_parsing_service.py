# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from uuid import UUID
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.orm import Session

from rag.config import get_settings
from rag.db.repository import PaperRepository
from rag.service.storage import StorageProvider
from rag.service.parser.parser_provider import ParserProvider
from rag.service.arxiv import make_arxiv_id_safe

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

    def parse_stored_pdf(self, paper_id: UUID) -> dict[str, str]:
        paper = None

        try:
            paper = self.paper_repository.get_by_id(paper_id)

            if paper is None:
                logger.warning("Paper not found for PDF parsing: paper_id=%s", paper_id)
                raise ValueError(f"Paper with id {paper_id} not found")

            if paper.pdf_object_key is None:
                logger.warning("Paper has no stored PDF: paper_id=%s", paper_id)
                raise ValueError(f"Paper with id {paper_id} has no stored PDF")

            safe_arxiv_id = make_arxiv_id_safe(paper.arxiv_id)

            logger.info(
                "Parsing stored paper PDF: paper_id=%s arxiv_id=%s",
                paper.id,
                paper.arxiv_id,
            )

            with TemporaryDirectory() as temp_dir:
                local_path = Path(temp_dir) / "original.pdf"

                logger.info(
                    "Obtaining paper PDF to local: object_key=%s local_path=%s",
                    paper.pdf_object_key,
                    local_path,
                )
                self.storage.download_file(
                    object_key=paper.pdf_object_key,
                    local_path=local_path,
                )

                logger.info("Parsing PDF from local path: local_path=%s", local_path)
                parsed = self.parser_provider.parse_pdf(local_path)

                json_object_key = f"arxiv/{safe_arxiv_id}/parsed/parsed_document.json"

                logger.info(
                    "Storing parsed text to storage in json format: json_object_key=%s",
                    json_object_key,
                )
                self.storage.upload_json(parsed.model_dump(), json_object_key)

            self.paper_repository.mark_parsed(
                paper=paper,
                parsed_json_object_key=json_object_key,
                parser_name=parsed.parser_name,
            )
            self.session.commit()

            logger.info(
                "Finished paper PDF parsing: paper_id=%s object_key=%s parser=%s",
                paper.id,
                json_object_key,
                parsed.parser_name,
            )

            return {
                "parsed_json_object_key": json_object_key,
                "parser_name": parsed.parser_name,
            }

        except ValueError as error:
            if paper is not None:
                self.paper_repository.mark_parse_failed(paper, str(error))
                self.session.commit()

            raise

        except Exception as error:
            if paper is not None:
                self.paper_repository.mark_parse_failed(paper, str(error))
                self.session.commit()

            logger.exception("Failed paper PDF parsing")
            raise RuntimeError("Failed paper PDF parsing") from error
