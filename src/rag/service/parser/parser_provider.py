# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path

import fitz

from rag.config import ParserSettings
from rag.schema.document_schema import ParsedDocument
from rag.service.parser.interface import ParserStrategy
from rag.service.parser.docling_parser import DoclingParser
from rag.service.parser.pymupdf_parser import PyMuPDFParser

logger = logging.getLogger(__name__)


class ParserProvider:
    """
    Selects PDF parser strategies and owns validation policy,
    through the `parse_pdf()` method.
    """

    def __init__(
        self,
        settings: ParserSettings,
        primary_parser: ParserStrategy | None = None,
        fallback_parser: ParserStrategy | None = None,
    ) -> None:
        self.enable_fallback_parser = settings.enable_fallback_parser
        self.max_pages = settings.max_pages
        self.max_file_size_bytes = settings.max_file_size_mb * 1024 * 1024
        self.primary_parser = primary_parser or DoclingParser(settings)
        self.fallback_parser = fallback_parser or PyMuPDFParser()

    def parse_pdf(self, pdf_path: Path) -> ParsedDocument:
        file_size, page_count = self._validate_pdf(pdf_path)

        try:
            parsed = self.primary_parser.parse(pdf_path)
            logger.info("Successful parsing with primary parser")

        except Exception as error:
            if not self.enable_fallback_parser:
                raise

            logger.warning(f"Primary parser failed to parse PDF: {str(error)}")

            parsed = self.fallback_parser.parse(pdf_path)
            parsed.metadata["primary_parser_error"] = str(error)

        parsed.metadata.update(
            {
                "file_size_bytes": file_size,
                "page_count": page_count,
            }
        )

        return parsed

    def _validate_pdf(self, pdf_path: Path) -> tuple[int, int]:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        file_size = pdf_path.stat().st_size

        if file_size == 0:
            raise ValueError(f"PDF is empty: {pdf_path}")

        if file_size > self.max_file_size_bytes:
            raise ValueError(
                "PDF file is too large: "
                f"{file_size / 1024 / 1024:.1f}MB > "
                f"{self.max_file_size_bytes / 1024 / 1024:.1f}MB"
            )

        with pdf_path.open("rb") as file:
            header = file.read(5)

        if header != b"%PDF-":
            raise ValueError(f"File is not a valid PDF: {pdf_path}")

        page_count = self._page_count(pdf_path)

        if page_count > self.max_pages:
            raise ValueError(f"PDF has too many pages: {page_count} > {self.max_pages}")

        return file_size, page_count

    def _page_count(self, pdf_path: Path) -> int:
        with fitz.open(pdf_path) as doc:
            return len(doc)
