# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID
from typing import Any
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from rag.db.model import ChunkIndexingStatus, ChunkModel, PaperModel
from rag.db.repository import ChunkRepository, PaperRepository
from rag.service.embedding import (
    EmbeddingProvider,
    ChunkEmbeddingService,
    ChunkEmbeddingResult,
)
from rag.service.elasticsearch.config import ElasticsearchClient


@dataclass(slots=True)
class EligibleChunk:
    chunk: ChunkModel
    paper: PaperModel

    @property
    def to_tuple(self) -> tuple[ChunkModel, PaperModel]:
        return (self.chunk, self.paper)


@dataclass(slots=True)
class ChunkIndexingResult:
    embedding_model_name: str
    requested_chunks: int
    indexed_chunks: int
    failed_chunks: int
    errors: dict[UUID, str]


class ChunkIndexingService:
    def __init__(
        self,
        session: Session,
        embedding_provider: EmbeddingProvider,
        elasticsearch_client: ElasticsearchClient,
    ) -> None:
        self.session = session
        self.chunk_repository = ChunkRepository(session)
        self.paper_repository = PaperRepository(session)

        self.chunk_embedding_service = ChunkEmbeddingService(
            session=session,
            embedding_provider=embedding_provider,
        )
        self.embedding_model_name = embedding_provider.model_name
        self.elasticsearch_client = elasticsearch_client

    async def index_pending_chunks(
        self,
        paper_id: UUID,
        limit: int = 50,
        include_failed: bool = False,
    ) -> ChunkIndexingResult:
        """
        inserting/indexing pending chunks from database to search db
        """
        self.elasticsearch_client.ensure_chunk_index()

        chunks = self.chunk_repository.list_pending_indexing(
            paper_id=paper_id,
            limit=limit,
            include_failed=include_failed,
        )

        # if no chunk found, nothing to index
        if not chunks:
            self._finalize_paper_indexing_status(paper_id)
            self.session.commit()

            return ChunkIndexingResult(
                embedding_model_name=self.embedding_model_name,
                requested_chunks=0,
                indexed_chunks=0,
                failed_chunks=0,
                errors={},
            )

        eligible_chunks: list[EligibleChunk] = []

        failed_count = 0
        errors_by_chunk_id: dict[UUID, str] = {}

        # buffer cache for paper
        # we need this to minimize querying the same paper row
        # when the loop of chunks below querying the same paper, lookup to buffer instead
        paper_cache: dict[UUID, PaperModel] = {}

        for chunk in chunks:
            # lookup existing paper
            paper = paper_cache.get(chunk.paper_id)

            # append if none
            if paper is None:
                paper = self.paper_repository.get_by_id(chunk.paper_id)
                paper_cache[chunk.paper_id] = paper

            # check again if from db is still none
            # if paper does not exist, means the chunk does not belong to any existing paper
            if paper is None:
                failed_count += 1

                error_message = f"the chunk id: {chunk.id} does not belong to a paper with id {chunk.paper_id}"
                errors_by_chunk_id[chunk.id] = error_message

                self.chunk_repository.mark_indexing_failed(chunk, error_message)
                continue

            # append eligible chunk
            eligible_chunks.append(
                EligibleChunk(
                    chunk=chunk,
                    paper=paper,
                )
            )

        # perform indexing to all eligible chunks
        result = await self._index_chunks(eligible_chunks)

        result.failed_chunks += failed_count
        result.errors.update(errors_by_chunk_id)

        self._finalize_paper_indexing_status(paper_id)
        self.session.commit()

        return result

    async def reindex_paper(self, paper_id: UUID) -> dict[str, Any]:
        paper = self.paper_repository.get_by_id(paper_id)

        if paper is None:
            return {
                "paper_found": False,
                "paper_id": str(paper_id),
                "arxiv_id": None,
                "embedding_model": self.embedding_model_name,
                "chunks_requested": 0,
                "chunks_indexed": 0,
                "chunks_failed": 0,
                "elasticsearch_documents_deleted": 0,
                "errors": [f"paper {paper_id} was not found"],
            }

        self.elasticsearch_client.ensure_chunk_index()

        # delete chunks by paper in elasticsearch, as well as reset its status on database
        delete_result = self.elasticsearch_client.delete_chunks_by_paper(str(paper.id))
        chunks = self.chunk_repository.reset_indexing_by_paper(paper.id)

        eligible_chunks = [EligibleChunk(chunk=chunk, paper=paper) for chunk in chunks]

        # start reindexing
        self.paper_repository.mark_indexing_started(paper)

        result = await self._index_chunks(eligible_chunks)

        response: dict[str, Any] = {
            "paper_found": True,
            "paper_id": str(paper.id),
            "arxiv_id": paper.arxiv_id,
            "embedding_model": result.embedding_model_name,
            "chunks_requested": result.requested_chunks,
            "chunks_indexed": result.indexed_chunks,
            "chunks_failed": result.failed_chunks,
            "elasticsearch_documents_deleted": delete_result.deleted,
            "errors": result.errors,
        }

        if not chunks:
            self.paper_repository.mark_indexing_skipped(paper)
        elif result.failed_chunks:
            self.paper_repository.mark_indexing_failed(paper)
        else:
            self.paper_repository.mark_indexed(paper)

        self.session.commit()

        return response

    async def _index_chunks(
        self,
        eligible_chunks: list[EligibleChunk],
    ) -> ChunkIndexingResult:
        """
        core chunk indexing operation

        embeds the exact chunks it was given via `ChunkEmbeddingService.embed_chunks()`
        rather than re-querying "pending embedding" chunks — `embedding_status` and
        `indexing_status` are independent columns, so a chunk can already be
        `EMBEDDED` while still `PENDING` indexing. re-querying would silently drop
        those chunks.
        """
        documents: list[dict[str, Any]] = []  # documents to be inserted
        embedded_chunks: dict[str, ChunkModel] = {}  # successful embedded chunks buffer

        failed_count = 0
        errors_by_chunk_id: dict[UUID, str] = {}

        chunks = [eligible.chunk for eligible in eligible_chunks]

        # initialized `started` indexing status for all chunk
        for chunk in chunks:
            self.chunk_repository.mark_indexing_started(chunk)

        # embed exactly the chunks we were handed, no re-query
        embedding_result: ChunkEmbeddingResult = (
            await self.chunk_embedding_service.embed_chunks(chunks)
        )

        # embedding lookup by chunk id
        embeddings_by_chunk_id = embedding_result.embeddings_by_chunk_id

        failed_count += embedding_result.failed_chunks
        errors_by_chunk_id.update(embedding_result.errors)

        # mark failed chunks to embed
        # this way we can keep track of missing/error chunk embedding
        # instead of processing directly to the loop of eligible_chunks below
        self._mark_missing_embeddings_indexing_failed(
            chunks=chunks,
            embeddings_by_chunk_id=embeddings_by_chunk_id,
            errors=embedding_result.errors,
        )

        for eligible in eligible_chunks:
            # extract field
            chunk, paper = eligible.to_tuple

            # get embedding by chunk id
            embedding = embeddings_by_chunk_id.get(chunk.id)

            # this would easily skipped the chunk that is marked as missing embeddings
            # the flow is very vague, but this is the simplest way
            if embedding is None:
                continue

            # build chunk document schema from `PaperModel` and `ChunkModel`
            document = self._build_chunk_document(
                chunk=chunk,
                paper=paper,
                embedding=embedding,
            )
            documents.append(document)

            # store successul embedded chunk to this buffer
            # we need it for the extra validation step after bulk insertion
            str_chunk_id = document["chunk_id"]
            embedded_chunks[str_chunk_id] = chunk

        # if no document was successfully built, return 0 result
        if not documents:
            return ChunkIndexingResult(
                embedding_model_name=self.embedding_model_name,
                requested_chunks=len(chunks),
                indexed_chunks=0,
                failed_chunks=failed_count,
                errors=errors_by_chunk_id,
            )

        # perform bulk indexing, failure can likely happen
        try:
            bulk_result = self.elasticsearch_client.bulk_index_chunks(documents)

        except Exception as error:
            # mark as error during bulk indexing
            for chunk in embedded_chunks.values():
                error_message = f"chunk {chunk.id} failed during bulk indexing: {error}"
                errors_by_chunk_id[chunk.id] = error_message

                self.chunk_repository.mark_indexing_failed(chunk, error_message)

            return ChunkIndexingResult(
                embedding_model_name=self.embedding_model_name,
                requested_chunks=len(chunks),
                indexed_chunks=0,
                # failed to embed + failed to bulk insert = a total of chunk processed in this function
                failed_chunks=failed_count + len(embedded_chunks),
                errors=errors_by_chunk_id,
            )

        indexed_count = 0

        # process bulk insertion result
        for item in bulk_result.items:
            document_id = item.id

            chunk = embedded_chunks.get(document_id)

            if chunk is None:
                continue

            # for a successful bulk inserted item
            if item.ok:
                indexed_count += 1
                self.chunk_repository.mark_indexed(chunk, document_id)
                continue

            # failed otherwise
            failed_count += 1

            error_message = (
                f"chunk id: {document_id} with Elasticsearch status of "
                f"{item.status}: {item.error}"
            )
            errors_by_chunk_id[chunk.id] = error_message

            self.chunk_repository.mark_indexing_failed(chunk, error_message)

        return ChunkIndexingResult(
            embedding_model_name=self.embedding_model_name,
            requested_chunks=len(chunks),
            indexed_chunks=indexed_count,
            failed_chunks=failed_count,
            errors=errors_by_chunk_id,
        )

    def _mark_missing_embeddings_indexing_failed(
        self,
        chunks: list[ChunkModel],
        embeddings_by_chunk_id: dict[UUID, list[float]],
        errors: dict[UUID, str],
    ) -> None:
        """
        mark missing chunk embeddings, as a failed process to embed chunk
        """
        for chunk in chunks:
            # chunk id validation
            # if chunk id exist in embeddings_by_chunk_id keys (chunk id) = eligible
            if chunk.id in embeddings_by_chunk_id:
                continue

            error_message = errors.get(chunk.id)

            if error_message is None:
                error_message = (
                    f"{chunk.id}: embedding failed"  # fallback error message
                )

            self.chunk_repository.mark_indexing_failed(chunk, error_message)

    def _finalize_paper_indexing_status(self, paper_id: UUID) -> None:
        paper = self.paper_repository.get_by_id(paper_id)

        if paper is None:
            return

        chunks = self.chunk_repository.list_by_paper_id(paper_id)

        if not chunks:
            self.paper_repository.mark_indexing_skipped(paper)
            return

        if any(chunk.indexing_status == ChunkIndexingStatus.FAILED for chunk in chunks):
            self.paper_repository.mark_indexing_failed(paper)
            return

        if all(
            chunk.indexing_status == ChunkIndexingStatus.INDEXED for chunk in chunks
        ):
            self.paper_repository.mark_indexed(paper)
            return

        self.paper_repository.mark_indexing_started(paper)

    def _build_chunk_document(
        self,
        chunk: ChunkModel,
        paper: PaperModel,
        embedding: list[float],
    ) -> dict[str, Any]:
        """
        map `ChunkModel` and `PaperModel` into elasticsearch mapping properties

        the keys must have matched the retured properties by `create_chunk_index_mapping()` function
        """

        return {
            "chunk_id": str(chunk.id),
            "paper_id": str(chunk.paper_id),
            "arxiv_id": paper.arxiv_id,
            "chunk_index": chunk.chunk_index,
            "chunk_text": chunk.text,
            "chunk_word_count": chunk.word_count,
            "section_title": chunk.section_title,
            "start_word": chunk.start_word,
            "end_word": chunk.end_word,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
            "overlap_with_previous": chunk.overlap_with_previous,
            "overlap_with_next": chunk.overlap_with_next,
            "source_storage_key": chunk.source_object_key,
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "categories": paper.categories,
            "published_date": paper.published_date.isoformat(),
            "pdf_url": paper.pdf_url,
            "pdf_storage_key": paper.pdf_object_key,
            "embedding": embedding,
            "embedding_model": self.embedding_model_name,
            "embedding_dimension": len(embedding),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
