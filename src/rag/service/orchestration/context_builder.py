# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from typing import Any

from rag.service.elasticsearch.config import SearchHit


@dataclass(frozen=True, slots=True)
class PaperMetadata:
    """
    Information about paper metadata responsible for building the knowledge context
    """

    paper_id: str
    arxiv_id: str
    title: str
    authors: list[str]
    categories: list[str]
    published_date: str
    pdf_url: str
    pdf_storage_key: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "categories": self.categories,
            "published_date": self.published_date,
            "pdf_url": self.pdf_url,
            "pdf_storage_key": self.pdf_storage_key,
        }


@dataclass(frozen=True, slots=True)
class Citation:
    """
    Citation is built from document chunks with paper metadata
    """

    source_number: int
    chunk_id: str
    paper_metadata: PaperMetadata
    section_title: str | None
    chunk_index: int
    score: float | None
    highlights: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_number": self.source_number,
            "chunk_id": self.chunk_id,
            **self.paper_metadata.to_dict(),
            "section_title": self.section_title,
            "chunk_index": self.chunk_index,
            "score": self.score,
            "highlights": self.highlights,
        }


@dataclass(frozen=True, slots=True)
class Source:
    """
    Source represent each unique paper that holds its citations
    """

    paper_source_number: int
    paper_metadata: PaperMetadata
    citation_numbers: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_source_number": self.paper_source_number,
            **self.paper_metadata.to_dict(),
            "citation_numbers": self.citation_numbers,
        }


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    """
    Response schema from `ContextBuilder` provides
    structured and prepared context to feed into LLMs
    """

    context_prompt: str
    citations: list[Citation]
    sources: list[Source]
    context_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_prompt": self.context_prompt,
            "citations": [citation.to_dict() for citation in self.citations],
            "sources": [source.to_dict() for source in self.sources],
            "context_size": self.context_size,
        }


class ContextBuilder:
    """
    ContextBuilder prepares retrieved search hits into prompt-ready context
    through `build_context()` method.
    """

    def __init__(
        self,
        max_chunk_size: int = 1_800,
        max_context_size: int | None = None,
    ) -> None:
        if max_chunk_size < 1:
            raise ValueError("max_chunk_chars must be greater than 0")

        if max_context_size is not None and max_context_size < 1:
            raise ValueError("max_context_chars must be greater than 0")

        self.max_chunk_size = max_chunk_size
        self.max_context_size = max_context_size

    def build_context(self, hits: list[SearchHit]) -> RetrievalContext:
        """
        Build retrieval context from Elasticsearch search hits.

        Duplicate chunk IDs and empty chunk text are skipped. Paper metadata is
        deduplicated into sources while citations keep chunk-level details.

        Args:
            hits:
                Retrieved chunk search hits ordered by retrieval relevance.
        """
        citations: list[Citation] = []
        source_blocks: list[str] = []
        seen_chunk_ids: set[str] = set()
        context_size = 0

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
                context_size=context_size,
                source_block=source_block,
            ):
                break

            citations.append(citation)
            source_blocks.append(source_block)
            seen_chunk_ids.add(chunk_id)

            context_size += len(source_block)

        full_context_prompt = "\n\n".join(source_blocks)

        return RetrievalContext(
            context_prompt=full_context_prompt,
            citations=citations,
            sources=self._make_deduplicated_sources(citations),
            context_size=context_size,
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
            paper_metadata=PaperMetadata(
                paper_id=self._string_value(source, "paper_id"),
                arxiv_id=self._string_value(source, "arxiv_id"),
                title=self._string_value(source, "title"),
                authors=self._string_list(source.get("authors", [])),
                categories=self._string_list(source.get("categories", [])),
                published_date=self._string_value(source, "published_date"),
                pdf_url=self._string_value(source, "pdf_url"),
                pdf_storage_key=self._optional_string_value(source, "pdf_storage_key"),
            ),
            section_title=self._optional_string_value(source, "section_title"),
            chunk_index=self._int_value(source, "chunk_index"),
            score=hit.score,
            highlights=hit.highlights,
        )

    def _make_source_block(
        self,
        citation: Citation,
        chunk_text: str,
    ) -> str:
        section_title = citation.section_title or "Unknown section"

        # each source only contains: title, arxiv id, section, and its content text
        # make it compact and only add necessary/useful information to the LLM
        return "\n".join(
            [
                f"[Source {citation.source_number}]",
                f"Title: {citation.paper_metadata.title}",
                f"arXiv ID: {citation.paper_metadata.arxiv_id}",
                f"Section: {section_title}",
                "Text:",
                chunk_text,
            ]
        )

    def _truncate_text(self, text: str) -> str:
        normalized = " ".join(text.split())

        if len(normalized) <= self.max_chunk_size:
            return normalized

        return normalized[: self.max_chunk_size].rstrip() + "..."

    def _would_exceed_context_limit(
        self,
        context_size: int,
        source_block: str,
    ) -> bool:
        if self.max_context_size is None:
            return False

        if not source_block:
            return False

        separator_chars = 2 if context_size else 0

        return (
            context_size + separator_chars + len(source_block)
            > self.max_context_size
        )

    def _make_deduplicated_sources(
        self,
        citations: list[Citation],
    ) -> list[Source]:
        source_indexes_by_key: dict[str, int] = {}
        sources: list[Source] = []

        for citation in citations:
            paper_metadata_key = self._paper_metadata_key(citation.paper_metadata)
            source_index = source_indexes_by_key.get(paper_metadata_key)

            if source_index is None:
                source_index = len(sources)
                source_indexes_by_key[paper_metadata_key] = source_index
                sources.append(
                    Source(
                        paper_source_number=source_index + 1,
                        paper_metadata=citation.paper_metadata,
                        citation_numbers=[],
                    )
                )

            sources[source_index].citation_numbers.append(citation.source_number)

        return sources

    def _paper_metadata_key(self, paper_metadata: PaperMetadata) -> str:
        """
        Somewhat return uniqueness that identifies the key,
        `paper_id` will likely be used most of the time, the rest are just fallback
        """
        if paper_metadata.paper_id:
            return paper_metadata.paper_id

        if paper_metadata.arxiv_id:
            return paper_metadata.arxiv_id

        return paper_metadata.pdf_url

    def _string_value(self, source: dict[str, Any], key: str) -> str:
        value = source.get(key)
        return "" if value is None else str(value)

    def _optional_string_value(self, source: dict[str, Any], key: str) -> str | None:
        value = source.get(key)
        return None if value is None else str(value)

    def _int_value(self, source: dict[str, Any], key: str) -> int:
        value = source.get(key)
        return 0 if value is None else int(value)

    def _string_list(self, values: Any) -> list[str]:
        return [str(value) for value in values] if isinstance(values, list) else []
