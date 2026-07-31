# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID
from datetime import datetime, timezone
from collections.abc import Iterable

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.orm import Session

from rag.db.model import (
    PaperModel,
    ChunkModel,
    ChunkEmbeddingStatus,
    ChunkIndexingStatus,
)
from rag.schema.chunk_schema import ChunkCandidate


class ChunkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_paper_id(self, paper_id: UUID) -> list[ChunkModel]:
        statement = (
            select(ChunkModel)
            .where(ChunkModel.paper_id == paper_id)
            .order_by(ChunkModel.chunk_index.asc())
        )
        return list(self.session.scalars(statement))

    def create_from_candidates(
        self,
        paper: PaperModel,
        candidates: Iterable[ChunkCandidate],
        source_object_key: str,
    ) -> list[ChunkModel]:
        chunks = []

        for c in candidates:
            chunk = ChunkModel(
                paper_id=paper.id,
                # arxiv_id=paper.arxiv_id,
                chunk_index=c.chunk_index,
                section_title=c.section_title,
                text=c.text,
                word_count=c.word_count,
                start_word=c.start_word,
                end_word=c.end_word,
                start_char=c.start_char,
                end_char=c.end_char,
                overlap_with_previous=c.overlap_with_previous,
                overlap_with_next=c.overlap_with_next,
                source_object_key=source_object_key,
                # pending by default
                embedding_status=ChunkEmbeddingStatus.PENDING,
                indexing_status=ChunkIndexingStatus.PENDING,
            )
            self.session.add(chunk)
            chunks.append(chunk)

        return chunks

    def delete_by_paper_id(self, paper_id: UUID) -> None:
        statement = delete(ChunkModel).where(ChunkModel.paper_id == paper_id)
        self.session.execute(statement)

    def replace_paper_chunks(
        self,
        paper: PaperModel,
        candidates: Iterable[ChunkCandidate],
        source_object_key: str,
    ) -> list[ChunkModel]:
        self.delete_by_paper_id(paper.id)

        return self.create_from_candidates(
            paper=paper,
            candidates=candidates,
            source_object_key=source_object_key,
        )

    def list_pending_embeddings(
        self,
        paper_id: UUID | None = None,
        limit: int = 50,
        include_failed: bool = False,
    ) -> list[ChunkModel]:
        statuses = [ChunkEmbeddingStatus.PENDING]

        if include_failed:
            statuses.append(ChunkEmbeddingStatus.FAILED)

        statement = (
            select(ChunkModel)
            .where(ChunkModel.embedding_status.in_(statuses))
            .order_by(ChunkModel.created_at.asc(), ChunkModel.chunk_index.asc())
            .limit(limit)
        )

        if paper_id is not None:
            statement = statement.where(ChunkModel.paper_id == paper_id)

        return list(self.session.scalars(statement))

    def list_pending_indexing(
        self,
        paper_id: UUID | None = None,
        limit: int = 50,
        include_failed: bool = False,
    ) -> list[ChunkModel]:
        statuses = [ChunkIndexingStatus.PENDING]

        if include_failed:
            statuses.append(ChunkIndexingStatus.FAILED)

        statement = (
            select(ChunkModel)
            .where(ChunkModel.indexing_status.in_(statuses))
            .order_by(ChunkModel.created_at.asc(), ChunkModel.chunk_index.asc())
            .limit(limit)
        )

        if paper_id is not None:
            statement = statement.where(ChunkModel.paper_id == paper_id)

        return list(self.session.scalars(statement))

    # def get_indexing_stats(self) -> dict[str, int | float | datetime | None]:
    #     total_chunks = self.session.scalar(select(func.count(ChunkModel.id))) or 0

    #     indexed_count = (
    #         self.session.scalar(
    #             select(func.count(ChunkModel.id)).where(
    #                 ChunkModel.indexing_status == ChunkIndexingStatus.INDEXED
    #             )
    #         )
    #         or 0
    #     )

    #     failed_count = (
    #         self.session.scalar(
    #             select(func.count(ChunkModel.id)).where(
    #                 ChunkModel.indexing_status == ChunkIndexingStatus.FAILED
    #             )
    #         )
    #         or 0
    #     )

    #     unique_papers = (
    #         self.session.scalar(select(func.count(distinct(ChunkModel.paper_id)))) or 0
    #     )

    #     last_indexed_at = self.session.scalar(select(func.max(ChunkModel.indexed_at)))

    #     avg_chunks_per_paper = (
    #         round(total_chunks / unique_papers, 2) if unique_papers else 0.0
    #     )

    #     return {
    #         "total_chunks": total_chunks,
    #         "indexed_count": indexed_count,
    #         "failed_index_count": failed_count,
    #         "unique_papers": unique_papers,
    #         "average_chunks_per_paper": avg_chunks_per_paper,
    #         "last_indexed_at": last_indexed_at,
    #     }

    def reset_indexing_by_paper(self, paper_id: UUID) -> list[ChunkModel]:
        chunks = self.list_by_paper_id(paper_id)

        for c in chunks:
            c.embedding_status = ChunkEmbeddingStatus.PENDING
            c.indexing_status = ChunkIndexingStatus.PENDING
            c.embedding_error = None
            c.indexing_error = None
            c.document_id = None
            c.indexed_at = None

        return chunks

    def mark_embedding_started(self, chunk: ChunkModel) -> ChunkModel:
        """
        mark this chunk as soon as we sent this chunk to generate embedding
        """
        chunk.embedding_status = ChunkEmbeddingStatus.PROCESSING
        chunk.embedding_error = None

        return chunk

    def mark_embedded(
        self,
        chunk: ChunkModel,
        model_name: str,
        dimension: int,
    ) -> ChunkModel:
        """
        mark this chunk when chunk is successfully embedded
        """
        chunk.embedding_status = ChunkEmbeddingStatus.EMBEDDED
        chunk.embedding_model = model_name
        chunk.embedding_dimension = dimension
        chunk.embedded_at = datetime.now(timezone.utc)
        chunk.embedding_error = None

        return chunk

    def mark_embedding_failed(self, chunk: ChunkModel, error: str) -> ChunkModel:
        """
        mark this chunk when embedding failed
        """
        chunk.embedding_status = ChunkEmbeddingStatus.FAILED
        chunk.embedding_error = error

        return chunk

    def mark_indexing_started(self, chunk: ChunkModel) -> ChunkModel:
        """
        mark this chunk as soon as we start indexing the chunk embedding
        """
        chunk.indexing_status = ChunkIndexingStatus.PROCESSING
        chunk.indexing_error = None

        return chunk

    def mark_indexed(self, chunk: ChunkModel, document_id: str) -> ChunkModel:
        """
        mark this chunk when chunk embedding is successfully indexed
        """
        chunk.indexing_status = ChunkIndexingStatus.INDEXED
        chunk.document_id = document_id
        chunk.indexed_at = datetime.now(timezone.utc)
        chunk.indexing_error = None

        return chunk

    def mark_indexing_failed(self, chunk: ChunkModel, error: str) -> ChunkModel:
        """
        mark this chunk when indexing the chunk embedding failed
        """
        chunk.indexing_status = ChunkIndexingStatus.FAILED
        chunk.indexing_error = error

        return chunk
