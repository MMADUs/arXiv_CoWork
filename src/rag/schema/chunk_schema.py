# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from pydantic import BaseModel


class ChunkCandidate(BaseModel):
    chunk_index: int
    section_title: str | None
    text: str
    word_count: int
    start_word: int
    end_word: int
    start_char: int
    end_char: int
    overlap_with_previous: int
    overlap_with_next: int
