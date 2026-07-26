# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from uuid import UUID
from dataclasses import dataclass

from sqlalchemy.orm import Session

from rag.db.model import ChunkModel
from rag.db.repository import ChunkRepository
from rag.service.embedding.config import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChunkEmbeddingResult:
    """
    main vector embedding result payload
    """

    embeddings_by_chunk_id: dict[UUID, list[float]]
    failed_chunks: int
    errors: dict[UUID, str]


@dataclass(slots=True)
class EmbedChunkResult:
    """
    `ChunkEmbeddingService` response payload
    """

    embedding_model_name: str
    requested_chunks: int
    embedded_count: int
    result: ChunkEmbeddingResult | None


class ChunkEmbeddingService:
    """
    `ChunkEmbeddingService` turn document chunks into vector embeddings,
    through `embed_pending_chunks()` method.
    """

    def __init__(
        self,
        session: Session,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.session = session
        self.chunk_repository = ChunkRepository(session)
        self.embedding_provider = embedding_provider

    async def embed_pending_chunks(
        self,
        paper_id: UUID | None = None,
        limit: int = 50,
        include_failed: bool = False,
    ) -> EmbedChunkResult:
        """
        queries chunks pending embedding and embeds them.
 
        `include_failed` includes previously-failed chunks as a retry.
        """
        chunks = self.chunk_repository.list_pending_embeddings(
            paper_id=paper_id,
            limit=limit,
            include_failed=include_failed,
        )
 
        # no chunks to embed
        if not chunks:
            return EmbedChunkResult(
                embedding_model_name=self.embedding_provider.model_name,
                requested_chunks=0,
                embedded_count=0,
                result=None,
            )
 
        result = await self.embed_chunks(chunks)
 
        self.session.commit()
 
        return EmbedChunkResult(
            embedding_model_name=self.embedding_provider.model_name,
            requested_chunks=len(chunks),
            embedded_count=len(result.embeddings_by_chunk_id),
            result=result,
        )
 
    async def embed_chunks(self, chunks: list[ChunkModel]) -> ChunkEmbeddingResult:
        """
        embeds an explicit list of chunks, regardless of their current
        `embedding_status`. 
        
        marks each chunk's embedding status as it goes
        (started / embedded / failed). does not commit because caller owns the transaction boundary.
        """
        if not chunks:
            return ChunkEmbeddingResult(
                embeddings_by_chunk_id={},
                failed_chunks=0,
                errors={},
            )
 
        for chunk in chunks:
            self.chunk_repository.mark_embedding_started(chunk)
 
        result = await self._divide_embed_batch(chunks)
 
        for chunk in chunks:
            embedding = result.embeddings_by_chunk_id.get(chunk.id)
 
            if embedding is None:
                continue
 
            self.chunk_repository.mark_embedded(
                chunk=chunk,
                model_name=self.embedding_provider.model_name,
                dimension=len(embedding),
            )
 
        return result

    async def _divide_embed_batch(
        self,
        chunks: list[ChunkModel],
    ) -> ChunkEmbeddingResult:
        """
        the embed chunk function that interacts with the embedding provider

        tries to embed the whole batch at once. if that fails, bisects the
        batch and retries each half, recursing only into halves that still
        fail (divide and conquer).
        """
        texts = [c.text for c in chunks]

        try:
            embeddings = await self.embedding_provider.embed_documents(texts)

            # if the total embeddings is not equal to total chunks
            # at least 1 chunk is not embedded, throw error.
            if len(embeddings) != len(chunks):
                raise ValueError(
                    f"Embedding count mismatch, expected {len(chunks)} found {len(embeddings)} instead"
                )

            embeddings_by_chunk_id = {
                c.id: emb for c, emb in zip(chunks, embeddings, strict=True)
            }

            return ChunkEmbeddingResult(
                embeddings_by_chunk_id=embeddings_by_chunk_id,
                failed_chunks=0,
                errors={},
            )

        except Exception as error:
            # base case: a single chunk still fails on its own, it's a
            # genuinely bad chunk (not just bad company in a batch)
            if len(chunks) == 1:
                chunk = chunks[0]
                error_message = f"Failed to embed chunk id {chunk.id}: {error}"

                self.chunk_repository.mark_embedding_failed(chunk, str(error))

                return ChunkEmbeddingResult(
                    embeddings_by_chunk_id={},
                    failed_chunks=1,
                    errors={chunk.id: error_message},
                )

            logger.warning(
                "Batch embedding failed for %d chunks, bisecting: %s",
                len(chunks),
                error,
            )

            midpoint = len(chunks) // 2

            # left-right recursize
            left_result = await self._divide_embed_batch(chunks[:midpoint])
            right_result = await self._divide_embed_batch(chunks[midpoint:])

            return ChunkEmbeddingResult(
                embeddings_by_chunk_id={
                    **left_result.embeddings_by_chunk_id,
                    **right_result.embeddings_by_chunk_id,
                },
                failed_chunks=left_result.failed_chunks + right_result.failed_chunks,
                errors={**left_result.errors, **right_result.errors},
            )
