# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from typing import Any

from rag.service.elasticsearch.config import SearchHit


@dataclass(frozen=True, slots=True)
class Citation:
    source_number: int
    chunk_id: str
    paper_id: str
    arxiv_id: str
    title: str
    section_title: str | None
    pdf_url: str
    chunk_index: int
    start_word: int
    end_word: int
    start_char: int
    end_char: int
    score: float | None
    highlights: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_number": self.source_number,
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "section_title": self.section_title,
            "pdf_url": self.pdf_url,
            "chunk_index": self.chunk_index,
            "start_word": self.start_word,
            "end_word": self.end_word,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "score": self.score,
            "highlights": self.highlights,
        }


@dataclass(frozen=True, slots=True)
class Source:
    paper_source_number: int
    paper_id: str
    arxiv_id: str
    title: str
    authors: list[str]
    categories: list[str]
    published_date: str
    pdf_url: str
    pdf_storage_key: str | None
    citation_numbers: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_source_number": self.paper_source_number,
            "paper_id": self.paper_id,
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "categories": self.categories,
            "published_date": self.published_date,
            "pdf_url": self.pdf_url,
            "pdf_storage_key": self.pdf_storage_key,
            "citation_numbers": self.citation_numbers,
        }


@dataclass(frozen=True, slots=True)
class BuiltContext:
    prompt_context: str
    citations: list[Citation]
    sources: list[Source]
    chunk_count: int
    context_char_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_context": self.prompt_context,
            "citations": [citation.to_dict() for citation in self.citations],
            "sources": [source.to_dict() for source in self.sources],
            "chunk_count": self.chunk_count,
            "context_char_count": self.context_char_count,
        }


class ContextBuilder:
    def __init__(
        self,
        max_chunk_chars: int = 1_800,
        max_context_chars: int | None = None,
    ) -> None:
        if max_chunk_chars < 1:
            raise ValueError("max_chunk_chars must be greater than 0")

        if max_context_chars is not None and max_context_chars < 1:
            raise ValueError("max_context_chars must be greater than 0")

        self.max_chunk_chars = max_chunk_chars
        self.max_context_chars = max_context_chars

    def build(self, hits: list[SearchHit]) -> BuiltContext:
        citations: list[Citation] = []
        source_blocks: list[str] = []
        seen_chunk_ids: set[str] = set()
        context_char_count = 0

        for hit in hits:
            chunk_id = hit.chunk_id

            if chunk_id in seen_chunk_ids:
                continue

            chunk_text = self._truncate_text(hit.chunk_text)

            if not chunk_text:
                continue

            source_number = len(citations) + 1
            citation = self._make_citation(
                source_number=source_number,
                hit=hit,
            )
            source_block = self._make_source_block(
                citation=citation,
                chunk_text=chunk_text,
            )

            if self._would_exceed_context_limit(
                context_char_count=context_char_count,
                source_block=source_block,
            ):
                break

            citations.append(citation)
            source_blocks.append(source_block)
            seen_chunk_ids.add(chunk_id)
            context_char_count += len(source_block)

        return BuiltContext(
            prompt_context="\n\n".join(source_blocks),
            citations=citations,
            sources=self._make_deduplicated_sources(
                citations=citations,
                hits=hits,
            ),
            chunk_count=len(citations),
            context_char_count=context_char_count,
        )

    def _make_citation(
        self,
        source_number: int,
        hit: SearchHit,
    ) -> Citation:
        source = hit.source

        return Citation(
            source_number=source_number,
            chunk_id=hit.chunk_id,
            paper_id=self._string_value(source, "paper_id"),
            arxiv_id=self._string_value(source, "arxiv_id"),
            title=self._string_value(source, "title"),
            section_title=self._optional_string_value(source, "section_title"),
            pdf_url=self._string_value(source, "pdf_url"),
            chunk_index=self._int_value(source, "chunk_index"),
            start_word=self._int_value(source, "start_word"),
            end_word=self._int_value(source, "end_word"),
            start_char=self._int_value(source, "start_char"),
            end_char=self._int_value(source, "end_char"),
            score=hit.score,
            highlights=hit.highlights,
        )

    def _make_source_block(
        self,
        citation: Citation,
        chunk_text: str,
    ) -> str:
        section_title = citation.section_title or "Unknown section"

        return "\n".join(
            [
                f"[Source {citation.source_number}]",
                f"Title: {citation.title}",
                f"arXiv ID: {citation.arxiv_id}",
                f"Section: {section_title}",
                f"Chunk ID: {citation.chunk_id}",
                f"Words: {citation.start_word}-{citation.end_word}",
                f"Characters: {citation.start_char}-{citation.end_char}",
                "Text:",
                chunk_text,
            ]
        )

    def _truncate_text(self, text: str) -> str:
        normalized = " ".join(text.split())

        if len(normalized) <= self.max_chunk_chars:
            return normalized

        return normalized[: self.max_chunk_chars].rstrip() + "..."

    def _would_exceed_context_limit(
        self,
        context_char_count: int,
        source_block: str,
    ) -> bool:
        if self.max_context_chars is None:
            return False

        if not source_block:
            return False

        separator_chars = 2 if context_char_count else 0

        return (
            context_char_count + separator_chars + len(source_block)
            > self.max_context_chars
        )

    def _make_deduplicated_sources(
        self,
        citations: list[Citation],
        hits: list[SearchHit],
    ) -> list[Source]:
        hit_lookup = {hit.chunk_id: hit for hit in hits}
        sources_by_key: dict[str, dict[str, Any]] = {}

        for citation in citations:
            source_key = self._source_key(citation)

            if source_key not in sources_by_key:
                hit = hit_lookup[citation.chunk_id]
                source = hit.source

                sources_by_key[source_key] = {
                    "paper_id": citation.paper_id,
                    "arxiv_id": citation.arxiv_id,
                    "title": citation.title,
                    "authors": self._string_list(source.get("authors", [])),
                    "categories": self._string_list(source.get("categories", [])),
                    "published_date": self._string_value(source, "published_date"),
                    "pdf_url": citation.pdf_url,
                    "pdf_storage_key": self._optional_string_value(
                        source,
                        "pdf_storage_key",
                    ),
                    "citation_numbers": [],
                }

            sources_by_key[source_key]["citation_numbers"].append(
                citation.source_number
            )

        sources: list[Source] = []

        for index, source in enumerate(sources_by_key.values(), start=1):
            sources.append(
                Source(
                    paper_source_number=index,
                    paper_id=source["paper_id"],
                    arxiv_id=source["arxiv_id"],
                    title=source["title"],
                    authors=source["authors"],
                    categories=source["categories"],
                    published_date=source["published_date"],
                    pdf_url=source["pdf_url"],
                    pdf_storage_key=source["pdf_storage_key"],
                    citation_numbers=source["citation_numbers"],
                )
            )

        return sources

    def _source_key(self, citation: Citation) -> str:
        if citation.paper_id:
            return citation.paper_id

        if citation.arxiv_id:
            return citation.arxiv_id

        return citation.pdf_url

    def _string_value(self, source: dict[str, Any], key: str) -> str:
        value = source.get(key, "")

        if value is None:
            return ""

        return str(value)

    def _optional_string_value(self, source: dict[str, Any], key: str) -> str | None:
        value = source.get(key)

        if value is None:
            return None

        return str(value)

    def _int_value(self, source: dict[str, Any], key: str) -> int:
        value = source.get(key, 0)

        if value is None:
            return 0

        return int(value)

    def _string_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []

        return [str(value) for value in values]
