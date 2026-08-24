# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from abc import ABC, abstractmethod
from pathlib import Path

from rag.schema.document_schema import ParsedDocument


class ParserStrategy(ABC):
    """
    Parser strategy contract for PDF-to-text extraction
    """

    @abstractmethod
    def parse(self, pdf_path: Path) -> ParsedDocument:
        """
        Parse a PDF file into a structured parsed document.
        """
