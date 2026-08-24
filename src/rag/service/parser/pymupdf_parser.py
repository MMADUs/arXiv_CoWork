# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from pathlib import Path

import fitz

from rag.service.parser.parser_interface import ParserStrategy
from rag.schema.document_schema import ParsedDocument, ParsedSection


class PyMuPDFParser(ParserStrategy):
    """
    PyMuPDF parser strategy for plain-text fallback extraction
    """

    def parse(self, pdf_path: Path) -> ParsedDocument:
        page_texts: list[str] = []

        with fitz.open(pdf_path) as doc:
            for page_idx, page in enumerate(doc):
                text = page.get_text("text")
                page_texts.append(f"Page {page_idx + 1}\n\n{text}")

        raw_text = "\n\n".join(page_texts)

        return ParsedDocument(
            raw_text=raw_text,
            sections=[
                ParsedSection(
                    title="Full text",
                    content=raw_text,
                )
            ],
            parser_name="pymupdf",
            metadata={
                "source_path": str(pdf_path),
            },
        )
