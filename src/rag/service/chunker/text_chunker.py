# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import re
from dataclasses import dataclass

from rag.config import ChunkerSettings
from rag.schema.document_schema import ParsedDocument, ParsedSection
from rag.schema.chunk_schema import ChunkCandidate
from rag.service.chunker.chunker_exceptions import ChunkerConfigurationError


@dataclass(slots=True)
class WordSpan:
    """
    Single token-like word span within a source text segment.

    Attributes:
        text: 
            Word text.
        start_char: 
            Character offset where the word starts within its source segment.
        end_char: 
            Character offset where the word ends within its source segment.
    """

    text: str
    start_char: int
    end_char: int


@dataclass(slots=True)
class SectionCandidate:
    """
    Normalized section-like text segment prepared for chunking.

    The character offsets are relative to the section content, while word offsets
    are relative to the full parsed document/chunking input.

    Attributes:
        title: 
            Section title or generated fallback title.
        content: 
            Section body text.
        start_word: 
            Word offset where this section starts.
        start_char: 
            Character offset where this section starts.
        words: 
            Word spans contained in this section.
    """

    title: str
    content: str
    start_word: int
    start_char: int
    words: list[WordSpan]

    @property
    def word_count(self) -> int:
        return len(self.words)

    @property
    def end_word(self) -> int:
        return self.start_word + self.word_count

    @property
    def end_char(self) -> int:
        if self.words:
            return self.start_char + self.words[-1].end_char

        return self.start_char + len(self.content)


class TextChunker:
    """
    strong deterministic baseline chunker

    the strategy is section-aware when parsed sections exist, but falls back to
    word-window chunking.

    filters obvious metadata sections, avoids abstract duplication,
    merges tiny sections, and splits large sections with overlap.
    """

    def __init__(self, settings: ChunkerSettings) -> None:
        if settings.overlap_words >= settings.target_chunk_words:
            raise ChunkerConfigurationError(
                "overlap_words must be less than target_chunk_words"
            )

        self.settings = settings

    def chunk_document(
        self,
        title: str,
        abstract: str,
        parsed_document: ParsedDocument,
    ) -> list[ChunkCandidate]:
        # parse `SectionCandidate`
        sections = self._prepare_sections(abstract, parsed_document)

        # if `section_based` chunking is disabled or no section candidates
        # we chunk raw text
        if not self.settings.section_based or not sections:
            return self._chunk_plain_text(
                title=title,
                abstract=abstract,
                raw_text=parsed_document.raw_text,
            )

        chunks: list[ChunkCandidate] = []

        # temp buffer to hold small sections
        small_sections: list[SectionCandidate] = []

        for index, section in enumerate(sections):
            # if a section is smaller than minimum word to be store in a chunk
            # we buffer the section
            if section.word_count < self.settings.min_chunk_words:
                small_sections.append(section)

                # check if we should flush small sections buffer
                # to make a chunk
                if self._should_flush_small_sections(
                    candidate_sections=sections,
                    current_index=index,
                ):
                    # flush buffer to make a chunk
                    self._append_small_section_chunks(
                        title=title,
                        abstract=abstract,
                        small_sections=small_sections,
                        chunks=chunks,
                    )
                    # reset buffer
                    small_sections = []

                continue

            # the remaining sections in small buffer
            # are appended to either previous chunk or be an individual chunk
            # this only happens when a normal/large section arrives after small section
            # due to the continue keyword
            if small_sections:
                self._append_small_section_chunks(
                    chunks=chunks,
                    title=title,
                    abstract=abstract,
                    small_sections=small_sections,
                )
                small_sections = []

            # else append section candidate to a chunk
            chunks.extend(
                self._chunk_section(
                    title=title,
                    abstract=abstract,
                    section=section,
                    base_index=len(chunks),
                )
            )

        # the remaining sections in small buffer
        # case where document sections ends with small sections, due to the continue keyword
        # are appended to either previous chunk or be an individual chunk
        if small_sections:
            self._append_small_section_chunks(
                chunks=chunks,
                title=title,
                abstract=abstract,
                small_sections=small_sections,
            )

        # if chunks exist, finalize by labeling each chunk with a number
        if chunks:
            return self._renumber_chunks(chunks)

        # make chunk from raw text (not sections)
        return self._chunk_plain_text(
            title=title,
            abstract=abstract,
            raw_text=parsed_document.raw_text,
        )

    def _prepare_sections(
        self,
        abstract: str,
        parsed_document: ParsedDocument,
    ) -> list[SectionCandidate]:
        abstract_words = set(abstract.lower().split())

        # parsed document must contains sections
        # otherwise use full raw text instead
        source_sections = parsed_document.sections or [
            ParsedSection(title="Full text", content=parsed_document.raw_text)
        ]
        candidate_sections: list[SectionCandidate] = []

        word_cursor = 0
        search_from = 0

        # process each parsed sections
        for section in source_sections:
            title = section.title.strip() if section.title else "Unknown"
            content = section.content.strip()

            if not content:
                continue

            # check if the content is worth skip
            # usually contains redundant information
            if self._should_skip_section(
                title=title,
                content=content,
                abstract=abstract,
                abstract_words=abstract_words,
            ):
                continue

            # find the start position index of content
            # from raw text
            start_char = self._find_section_start(
                raw_text=parsed_document.raw_text,
                content=content,
                search_from=search_from,
            )

            words = self._word_spans(content)

            if not words:
                continue

            candidate_sections.append(
                SectionCandidate(
                    title=title,
                    content=content,
                    start_word=word_cursor,
                    start_char=start_char,
                    words=words,
                )
            )

            word_cursor += len(words)
            search_from = max(search_from, start_char + len(content))

        return candidate_sections

    def _should_skip_section(
        self,
        title: str,
        content: str,
        abstract: str,
        abstract_words: set[str],
    ) -> bool:
        """
        check if we should skip section based on a rule based assumptions:

        section title looks like defined metadata,
        content contains duplicated abstract (because later we append abstract),
        and when content seem to be very short (potential metadata)
        """
        if self._is_metadata_section(title):
            return True

        if self._is_duplicate_abstract(content, abstract, abstract_words):
            return True

        if len(content.split()) < 20 and self._is_metadata_content(content):
            return True

        return False

    def _is_metadata_section(self, title: str) -> bool:
        """
        rule based checking if a section title is a metadata,
        might not work for all kinds of paper
        """
        title = title.lower().strip()

        # NOTE: predefined metadata titles as assumptions
        # might not cover all kinds of paper, so this is pretty naive
        metadata_titles = {
            "author",
            "authors",
            "affiliation",
            "affiliations",
            "email",
            "emails",
            "header",
            "metadata",
            "preprint",
            "submitted",
            "received",
            "accepted",
        }

        if title in metadata_titles:
            return True

        # NOTE: predefined metadata indicators as assumptions
        # might not cover all kinds of paper, so this is pretty naive
        metadata_indicators = (
            "affiliation",
            "department",
            "university",
            "institute",
            "arxiv",
            "preprint",
        )

        return any(
            indicator in title and len(title) < 40 for indicator in metadata_indicators
        )

    def _is_duplicate_abstract(
        self,
        content: str,
        abstract: str,
        abstract_words: set[str],
    ) -> bool:
        """
        check if a content is a duplicate of the abstract,
        currently intersection score must be above 80% to indicate a duplicate
        """
        # set all words to lowercase to compare
        content_lower = content.lower().strip()
        abstract_lower = abstract.lower().strip()

        if not content_lower or not abstract_lower:
            return False

        if abstract_lower in content_lower or content_lower in abstract_lower:
            return True

        if len(abstract_words) <= 10:
            return False

        content_words = set(content_lower.split())
        overlap = len(abstract_words.intersection(content_words))

        # NOTE: we set a threshold of 80% similarity by words
        # if a score pass this threshold we mark as duplicates
        return overlap / len(abstract_words) > 0.8

    def _is_metadata_content(self, content: str) -> bool:
        content_lower = content.lower()

        metadata_patterns = (
            "@",
            "arxiv:",
            "gmail.com",
            "edu",
            "ac.uk",
            "university",
            "institute",
            "department",
            "preprint",
        )

        matches = sum(1 for pattern in metadata_patterns if pattern in content_lower)

        return matches >= 2

    def _find_section_start(
        self,
        raw_text: str,
        content: str,
        search_from: int,
    ) -> int:
        """
        find the character offset where a parsed section's content starts
        in the document raw text
        """
        if not raw_text:
            return 0

        found_at = raw_text.find(content, search_from)

        if found_at >= 0:
            return found_at

        found_at = raw_text.find(content)

        if found_at >= 0:
            return found_at

        return search_from

    def _should_flush_small_sections(
        self,
        candidate_sections: list[SectionCandidate],
        current_index: int,
    ) -> bool:
        """
        validate if smaller sections should be flushed out of buffer into a chunk

        usually when we reached the last section or the next chunk is big enough
        """
        # if reaching the last section
        if current_index == len(candidate_sections) - 1:
            return True

        # check if the next section is large enough
        # so we flush the current sections from buffer to a chunk
        next_candidate_section = candidate_sections[current_index + 1]

        return next_candidate_section.word_count >= self.settings.min_chunk_words

    def _append_small_section_chunks(
        self,
        title: str,
        abstract: str,
        small_sections: list[SectionCandidate],
        chunks: list[ChunkCandidate],
    ) -> None:
        """
        flush small sections into a chunk candidate
        """
        if not small_sections:
            return

        # merge many small section candidate into 1 section candidate
        merged = self._merge_sections(small_sections)

        # even after we merge into 1 section candidate
        # sometimes the merged section candidate is still too small
        #
        # here we check if we have existing chunk
        # and if the merged section candidate is too small
        # and if the previous chunk + this section candidate size can fit the target size
        if (
            chunks
            and merged.word_count < self.settings.min_chunk_words
            and chunks[-1].word_count + merged.word_count
            <= self.settings.target_chunk_words
        ):
            # merge previous chunk with the merged section candidate
            chunks[-1] = self._merge_chunk_with_section(
                chunk=chunks[-1],
                title=title,
                abstract=abstract,
                section=merged,
            )
            return

        # else just pass the section candidate to make a chunk
        chunks.extend(
            self._chunk_section(
                title=title,
                abstract=abstract,
                section=merged,
                base_index=len(chunks),
            )
        )

    def _merge_sections(
        self,
        sections: list[SectionCandidate],
    ) -> SectionCandidate:
        """
        merge many small sections into 1 section candidate
        """
        # make a new title from many section title
        # by merging all title, but capped at 3, the rest is stated as (n-3) more
        title = " + ".join(section.title for section in sections[:3])

        if len(sections) > 3:
            title += f" + {len(sections) - 3} more"

        content = "\n\n".join(
            f"Section: {section.title}\n\n{section.content}" for section in sections
        )

        first = sections[0]
        words = self._word_spans(content)

        return SectionCandidate(
            title=title,
            content=content,
            start_word=first.start_word,
            start_char=first.start_char,
            words=words,
        )

    def _merge_chunk_with_section(
        self,
        chunk: ChunkCandidate,
        title: str,
        abstract: str,
        section: SectionCandidate,
    ) -> ChunkCandidate:
        """
        merge a chunk with a section candidate
        """
        # make new title by merging chunk title with section title
        section_title = (
            f"{chunk.section_title} + {section.title}"
            if chunk.section_title
            else section.title
        )

        # merge both content
        section_content = (
            f"{self._content_from_chunk_text(chunk.text)}\n\n"
            f"Section: {section.title}\n\n"
            f"{section.content}"
        )

        words = self._word_spans(section_content)

        return self._make_chunk(
            title=title,
            abstract=abstract,
            section_title=section_title,
            content=section_content,
            words=words,
            chunk_index=chunk.chunk_index,
            start_word=chunk.start_word,
            start_char=chunk.start_char,
            overlap_with_previous=chunk.overlap_with_previous,
            overlap_with_next=0,
        )

    def _content_from_chunk_text(self, chunk_text: str) -> str:
        """
        extract content from a string of chunk
        """
        marker = "\n\nContent:\n"

        if marker in chunk_text:
            return chunk_text.split(marker, maxsplit=1)[1]

        return chunk_text

    def _chunk_section(
        self,
        title: str,
        abstract: str,
        section: SectionCandidate,
        base_index: int,
    ) -> list[ChunkCandidate]:
        """
        make a chunk from the given section candidate
        """
        # only make chunk when it fits the target size
        if section.word_count <= self.settings.target_chunk_words:
            return [
                self._make_chunk(
                    title=title,
                    abstract=abstract,
                    section_title=section.title,
                    content=section.content,
                    words=section.words,
                    chunk_index=base_index,
                    start_word=section.start_word,
                    start_char=section.start_char,
                    overlap_with_previous=0,
                    overlap_with_next=0,
                )
            ]

        # when the section is too big
        # we have to split them so we can fit in the target size
        return self._split_large_section(
            title=title,
            abstract=abstract,
            section=section,
            base_index=base_index,
        )

    def _split_large_section(
        self,
        title: str,
        abstract: str,
        section: SectionCandidate,
        base_index: int,
    ) -> list[ChunkCandidate]:
        """
        split large section into smaller overlapping chunks
        """
        chunks: list[ChunkCandidate] = []

        step = self.settings.target_chunk_words - self.settings.overlap_words
        start = 0

        while start < section.word_count:
            end = min(start + self.settings.target_chunk_words, section.word_count)
            words = section.words[start:end]
            local_start_char = words[0].start_char
            local_end_char = words[-1].end_char
            content = section.content[local_start_char:local_end_char].strip()
            overlap_with_previous = min(self.settings.overlap_words, start)
            overlap_with_next = (
                self.settings.overlap_words if end < section.word_count else 0
            )

            section_title = f"{section.title} (Part {len(chunks) + 1})"

            chunks.append(
                self._make_chunk(
                    title=title,
                    abstract=abstract,
                    section_title=section_title,
                    content=content,
                    words=words,
                    chunk_index=base_index + len(chunks),
                    start_word=section.start_word + start,
                    start_char=section.start_char + local_start_char,
                    overlap_with_previous=overlap_with_previous,
                    overlap_with_next=overlap_with_next,
                )
            )

            if end == section.word_count:
                break

            start += step

        return chunks

    def _chunk_plain_text(
        self,
        title: str,
        abstract: str,
        raw_text: str,
    ) -> list[ChunkCandidate]:
        """
        dump raw text into section candidate,
        and let the other method handles when the chunk is too big
        """
        content = raw_text.strip()

        if not content:
            return []

        section = SectionCandidate(
            title="Full Text",
            content=content,
            start_word=0,
            start_char=0,
            words=self._word_spans(content),
        )

        # since we got a raw full text of section candidate,
        # let this method handle the section split
        # when section is too large to be a chunk
        return self._chunk_section(
            title=title,
            abstract=abstract,
            section=section,
            base_index=0,
        )

    def _make_chunk(
        self,
        title: str,
        abstract: str,
        section_title: str | None,
        content: str,
        words: list[WordSpan],
        chunk_index: int,
        start_word: int,
        start_char: int,
        overlap_with_previous: int,
        overlap_with_next: int,
    ) -> ChunkCandidate:
        """
        build the chunk candidate
        """
        normalized_content = self._sanitize_text(content).strip()

        # each chunk includes:
        # title, abstract, section title, and content
        context_title, context_abstract = self._paper_context(
            title=self._sanitize_text(title),
            abstract=self._sanitize_text(abstract),
        )
        normalized_section_title = (
            self._sanitize_text(section_title) if section_title else None
        )

        text = (
            f"Title: {context_title}\n\n"
            f"Abstract: {context_abstract}\n\n"
            f"Section: {normalized_section_title or 'Unknown'}\n\n"
            f"Content:\n{normalized_content}"
        )

        word_count = len(words)
        end_char = start_char

        if words:
            local_start = words[0].start_char
            local_end = words[-1].end_char
            end_char = start_char + (local_end - local_start)

        return ChunkCandidate(
            chunk_index=chunk_index,
            section_title=normalized_section_title,
            text=text,
            word_count=word_count,
            start_word=start_word,
            end_word=start_word + word_count,
            start_char=start_char,
            end_char=end_char,
            overlap_with_previous=overlap_with_previous,
            overlap_with_next=overlap_with_next,
        )

    def _paper_context(self, title: str, abstract: str) -> tuple[str, str]:
        """
        cap paper-level context while always prioritizing title before abstract
        """
        context_budget = self.settings.max_context_words

        if context_budget <= 0:
            return "", ""

        title_words = self._truncate_words(title, context_budget)
        remaining_budget = context_budget - len(title_words.split())

        abstract_words = self._truncate_words(abstract, remaining_budget)

        return title_words, abstract_words

    def _truncate_words(self, text: str, max_words: int) -> str:
        if max_words <= 0:
            return ""

        words = text.split()

        if len(words) <= max_words:
            return text.strip()

        return " ".join(words[:max_words])

    def _renumber_chunks(
        self,
        chunks: list[ChunkCandidate],
    ) -> list[ChunkCandidate]:
        """
        label each chunk with an index correspond to the parsed document
        """
        return [
            chunk.model_copy(update={"chunk_index": index})
            for index, chunk in enumerate(chunks)
        ]

    def _word_spans(self, text: str) -> list[WordSpan]:
        """
        build word span from a string of text
        """
        return [
            WordSpan(
                text=match.group(0),
                start_char=match.start(),
                end_char=match.end(),
            )
            for match in re.finditer(r"\S+", text)
        ]

    def _sanitize_text(self, text: str) -> str:
        return text.replace("\x00", "")
