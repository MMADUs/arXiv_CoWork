# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from rag.db.config import Base


class ChunkEmbeddingStatus(StrEnum):
    """ 
    Chunk embedding status string enum class

    Available enum members:
    - PENDING
    - PROCESSING
    - INDEXED
    - FAILED
    """
    PENDING = "pending"
    PROCESSING = "processing"
    EMBEDDED = "embedded"
    FAILED = "failed"


class ChunkIndexingStatus(StrEnum):
    """ 
    Chunk indexing status string enum class

    Available enum members:
    - PENDING
    - PROCESSING
    - INDEXED
    - FAILED
    """
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class ChunkModel(Base):
    __tablename__ = "chunks"

    # primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # link to paper id (foreign key)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id"), index=True
    )

    # arxiv_id: Mapped[str] = mapped_column(String(64), index=True)

    # document id of an embedded chunk from nosql db (eg: vector db)
    document_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    # chunk metadata
    chunk_index: Mapped[int] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    start_word: Mapped[int] = mapped_column(Integer)  # index position
    end_word: Mapped[int] = mapped_column(Integer)  # index position
    start_char: Mapped[int] = mapped_column(Integer, default=0)
    end_char: Mapped[int] = mapped_column(Integer, default=0)
    overlap_with_previous: Mapped[int] = mapped_column(Integer, default=0)
    overlap_with_next: Mapped[int] = mapped_column(Integer, default=0)

    # the parsed source where this chunk belongs to
    source_object_key: Mapped[str] = mapped_column(Text)

    # embedding metadata
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # status
    embedding_status: Mapped[str] = mapped_column(
        String(32),
        default=ChunkEmbeddingStatus.PENDING,
    )
    indexing_status: Mapped[str] = mapped_column(
        String(32),
        default=ChunkIndexingStatus.PENDING,
    )

    indexing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # date metadata
    embedded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
