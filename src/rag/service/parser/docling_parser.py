# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DocItemLabel

from rag.config import ParserSettings
from rag.service.parser.parser_interface import ParserStrategy
from rag.schema.document_schema import ParsedDocument, ParsedSection


class DoclingParser(ParserStrategy):
    """
    Docling parser strategy for structured scientific PDF extraction
    """

    def __init__(self, settings: ParserSettings) -> None:
        self.parsing_timeout = settings.parsing_timeout
        self.do_ocr = settings.do_ocr
        self.do_table_structure = settings.do_table_structure
        self.max_pages = settings.max_pages
        self.max_file_size_bytes = settings.max_file_size_mb * 1024 * 1024
        self.converter = self._create_converter()

    def _create_converter(self) -> DocumentConverter:
        pipeline_opt = PdfPipelineOptions(
            do_ocr=self.do_ocr,
            do_table_structure=self.do_table_structure,
            document_timeout=self.parsing_timeout,
        )

        if self.do_table_structure:
            pipeline_opt.table_structure_options.mode = TableFormerMode.ACCURATE
            pipeline_opt.table_structure_options.do_cell_matching = True

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opt)
            }
        )

    def parse(self, pdf_path: Path) -> ParsedDocument:
        result = self.converter.convert(
            str(pdf_path),
            max_num_pages=self.max_pages,
            max_file_size=self.max_file_size_bytes,
        )
        document = result.document

        raw_text = document.export_to_text()
        sections = self._sections_from_document(document)

        if not sections:
            sections = self._sections_from_text(raw_text)

        return ParsedDocument(
            raw_text=raw_text,
            sections=sections,
            parser_name="docling",
            metadata={
                "source_path": str(pdf_path),
                "with_ocr": self.do_ocr,
                "with_table_structure": self.do_table_structure,
            },
        )

    def _sections_from_document(self, document: Any) -> list[ParsedSection]:
        """
        Parse docling document structure into `ParsedSection`

        to understand about docling document structure, visit: 
        https://docling-project.github.io/docling/reference/docling_document/
        """
        sections: list[ParsedSection] = []

        # we set this to `top-content` by default
        # for edge cases when pdf starts with content without title/section-header
        current_title = "top-content"
        current_content: list[str] = []

        for element in document.texts:
            # docling document comes in format of label (header type) and text (the content)
            label = getattr(element, "label", None)
            text = getattr(element, "text", "")

            if not text or not text.strip():
                continue  # continue if content is empty

            # only append new section to `title` and `section_header`
            # the rest of the document label is treated as content
            if label in {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}:
                # if next label is met but content is filled
                # flush them by appending it as a section
                if current_content:
                    sections.append(
                        ParsedSection(
                            title=current_title,
                            content="\n".join(current_content).strip(),
                        )
                    )

                # set new title and clear content for next section
                current_title = text.strip()
                current_content = []
                continue

            # append to the current content
            # where the document label is neither `title` or `section_header`
            current_content.append(text.strip())

        # if current content still exist
        # append the leftover because the loop does not catch any `title` or `section_header` to append
        if current_content:
            sections.append(
                ParsedSection(
                    title=current_title,
                    content="\n".join(current_content).strip(),
                )
            )

        return sections

    def _sections_from_text(self, raw_text: str) -> list[ParsedSection]:
        """
        Fallback when we just want to dump the full raw text into 1 `ParsedSection`
        """
        if not raw_text.strip():
            return []

        # only 1 parsed section as full text
        return [
            ParsedSection(
                title="Full text",
                content=raw_text,
            )
        ]
