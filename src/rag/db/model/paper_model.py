# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import uuid

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, String, Text, Integer
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rag.db.config import Base


class PaperIngestionStatus(StrEnum):
    PENDING = "pending"
    METADATA_FETCHED = "metadata_fetched"
    METADATA_FAILED = "metadata_failed"
    PDF_DOWNLOADING = "pdf_downloading"
    PDF_STORED = "pdf_stored"
    PDF_FAILED = "pdf_failed"


class PaperParserStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class PaperChunkingStatus(StrEnum):
    PENDING = "pending"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    NO_CHUNKS = "no_chunks"
    FAILED = "failed"


class PaperIndexingStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class PaperModel(Base):
    __tablename__ = "papers"

    # primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # paper metadata
    arxiv_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    version: Mapped[int| None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(ARRAY(String))
    abstract: Mapped[str] = mapped_column(Text)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String))
    published_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pdf_url: Mapped[str] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(Text, nullable=True)

    # object key from storage
    pdf_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_download_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_json_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    # identify which parser tool is used to parse pdf to text
    parser_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # store parser error message
    parser_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # store chunking error message
    chunking_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # store paper-level indexing workflow error message
    indexing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # status
    ingestion_status: Mapped[str] = mapped_column(
        String(32), default=PaperIngestionStatus.PENDING
    )
    parser_status: Mapped[str] = mapped_column(
        String(32), default=PaperParserStatus.PENDING
    )
    chunking_status: Mapped[str] = mapped_column(
        String(32), default=PaperChunkingStatus.PENDING
    )
    indexing_status: Mapped[str] = mapped_column(
        String(32), default=PaperIndexingStatus.PENDING
    )

    # date metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
