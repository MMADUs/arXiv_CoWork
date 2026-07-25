# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from pydantic import BaseModel, Field


class ParsedSection(BaseModel):
    title: str
    content: str
    header_level: int = 1


class ParsedDocument(BaseModel):
    raw_text: str
    sections: list[ParsedSection]
    parser_name: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
