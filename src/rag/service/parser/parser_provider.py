# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from pathlib import Path

import fitz

from rag.config import ParserSettings
from rag.schema.document_schema import ParsedDocument
from rag.service.parser.docling_parser import DoclingParser
from rag.service.parser.exceptions import (
    ParserExecutionError,
    ParserPdfValidationError,
    ParserServiceError,
)
from rag.service.parser.interface import ParserStrategy
from rag.service.parser.pymupdf_parser import PyMuPDFParser

logger = logging.getLogger(__name__)


class ParserProvider:
    """
    Selects PDF parser strategies and owns validation policy,
    runs through the `parse_pdf()` method.
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
        """ 
        Raises:
            ParserPdfValidationError: 
                if the PDF is missing, empty, too large, or invalid.
            ParserExecutionError: 
                if PDF inspection, reading, or parser execution fails.
            ParserServiceError: 
                if a parser strategy raises another parser service error.
        """
        file_size, page_count = self._validate_pdf(pdf_path)

        try:
            return self._parse_with_primary(pdf_path, file_size, page_count)

        except ParserExecutionError as primary_error:
            if not self.enable_fallback_parser:
                raise

            logger.warning("Primary parser failed to parse PDF: %s", primary_error)
            parsed = self._parse_with_fallback(pdf_path, primary_error)

            parsed.metadata.update(
                {
                    "file_size_bytes": file_size,
                    "page_count": page_count,
                }
            )

            return parsed

    def _parse_with_primary(
        self,
        pdf_path: Path,
        file_size: int,
        page_count: int,
    ) -> ParsedDocument:
        parsed = self._parse_with_strategy(self.primary_parser, pdf_path)
        logger.info("Successful parsing with primary parser")
        parsed.metadata.update(
            {
                "file_size_bytes": file_size,
                "page_count": page_count,
            }
        )
        return parsed

    def _parse_with_fallback(
        self,
        pdf_path: Path,
        primary_error: ParserExecutionError,
    ) -> ParsedDocument:
        parsed = self._parse_with_strategy(self.fallback_parser, pdf_path)
        parsed.metadata["primary_parser_error"] = str(primary_error)
        return parsed

    def _parse_with_strategy(
        self,
        parser: ParserStrategy,
        pdf_path: Path,
    ) -> ParsedDocument:
        try:
            return parser.parse(pdf_path)

        except ParserServiceError:
            raise

        except Exception as error:
            raise ParserExecutionError("Failed to parse PDF document") from error

    def _validate_pdf(self, pdf_path: Path) -> tuple[int, int]:
        if not pdf_path.exists():
            raise ParserPdfValidationError(f"PDF not found: {pdf_path}")

        try:
            file_size = pdf_path.stat().st_size

        except OSError as error:
            raise ParserExecutionError(
                f"Failed to inspect PDF file: {pdf_path}"
            ) from error

        if file_size == 0:
            raise ParserPdfValidationError(f"PDF is empty: {pdf_path}")

        if file_size > self.max_file_size_bytes:
            raise ParserPdfValidationError(
                "PDF file is too large: "
                f"{file_size / 1024 / 1024:.1f}MB > "
                f"{self.max_file_size_bytes / 1024 / 1024:.1f}MB"
            )

        try:
            with pdf_path.open("rb") as file:
                header = file.read(5)

        except OSError as error:
            raise ParserExecutionError(
                f"Failed to read PDF file: {pdf_path}"
            ) from error

        if header != b"%PDF-":
            raise ParserPdfValidationError(f"File is not a valid PDF: {pdf_path}")

        page_count = self._page_count(pdf_path)

        if page_count > self.max_pages:
            raise ParserPdfValidationError(
                f"PDF has too many pages: {page_count} > {self.max_pages}"
            )

        return file_size, page_count

    def _page_count(self, pdf_path: Path) -> int:
        try:
            with fitz.open(pdf_path) as doc:
                return len(doc)

        except (RuntimeError, ValueError, OSError) as error:
            raise ParserPdfValidationError(
                f"Failed to read PDF page count: {pdf_path}"
            ) from error
