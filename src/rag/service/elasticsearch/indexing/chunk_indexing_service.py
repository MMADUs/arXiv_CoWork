# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from rag.db.model import (
    ChunkEmbeddingStatus,
    ChunkIndexingStatus,
    ChunkModel,
    PaperChunkingStatus,
    PaperModel,
)
from rag.db.repository import ChunkRepository, PaperRepository
from rag.service.embedding import (
    ChunkEmbeddingService,
    ChunkEmbeddingResult,
    EmbeddingProvider,
    EmbeddingServiceError,
)
from rag.service.elasticsearch.config import ElasticsearchClient
from rag.service.elasticsearch.es_exceptions import (
    ElasticsearchPaperNotFoundError,
    ElasticsearchPersistenceError,
    ElasticsearchServiceError,
)


@dataclass(slots=True)
class EligibleChunk:
    """
    Holds the eligible chunk for indexing
    """

    chunk: ChunkModel
    paper: PaperModel

    @property
    def to_tuple(self) -> tuple[ChunkModel, PaperModel]:
        return (self.chunk, self.paper)


@dataclass(slots=True)
class ChunkIndexingResult:
    """
    Response schema after the chunks are processed for indexing
    """

    embedding_model_name: str
    requested_chunks: int
    indexed_chunks: int
    failed_chunks: int
    errors: dict[UUID, str]


@dataclass(slots=True)
class PaperReindexResult:
    """
    Response schema after chunks are processed for reindex (update)
    """

    embedding_model_name: str
    requested_chunks: int
    indexed_chunks: int
    failed_chunks: int
    errors: dict[UUID, str]


class ChunkIndexingService:
    """
    `ChunkIndexingService` embeds paper chunks and indexes them into Elasticsearch,
    through `index_pending_chunks()` and `reindex_paper()` methods.
    """

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

    async def index_chunks_by_paper_id(
        self,
        paper_id: UUID,
        limit: int = 50,
        include_failed: bool = False,
    ) -> ChunkIndexingResult:
        """
        Insert/index pending chunks from database to search db.

        Returns:
            chunk indexing summary for the requested paper

        Raises:
            ElasticsearchPaperNotFoundError:
                if paper does not exist locally
            ElasticsearchIndexError:
                if Elasticsearch index setup fails
            ElasticsearchBulkIndexError:
                if Elasticsearch bulk indexing fails before per-chunk errors
                can be recorded
            ElasticsearchPersistenceError:
                if local indexing state persistence fails
        """
        try:
            paper = self.paper_repository.get_by_id(paper_id)

            if paper is None:
                raise ElasticsearchPaperNotFoundError(f"Paper not found: {paper_id}")

            if paper.chunking_status != PaperChunkingStatus.CHUNKED:
                return ChunkIndexingResult(
                    embedding_model_name=self.embedding_model_name,
                    requested_chunks=0,
                    indexed_chunks=0,
                    failed_chunks=0,
                    errors={},
                )

            self.elasticsearch_client.ensure_chunk_index()

            chunks = self.chunk_repository.list_pending_indexing(
                paper_id=paper_id,
                limit=limit,
                include_failed=include_failed,
            )

            # if no chunk found, nothing to index
            if not chunks:
                self._sync_paper_indexing_status(paper)
                self.session.commit()

                return ChunkIndexingResult(
                    embedding_model_name=self.embedding_model_name,
                    requested_chunks=0,
                    indexed_chunks=0,
                    failed_chunks=0,
                    errors={},
                )

            self.paper_repository.mark_indexing_started(paper)

            eligible_chunks = [
                EligibleChunk(chunk=chunk, paper=paper) for chunk in chunks
            ]

            # perform indexing to all eligible chunks
            result = await self._index_chunks(eligible_chunks)

            self._sync_paper_indexing_status(paper)
            self.session.commit()

            return result

        except ElasticsearchServiceError:
            self.session.rollback()
            raise

        except SQLAlchemyError as error:
            self.session.rollback()
            raise ElasticsearchPersistenceError(
                "Failed to persist paper indexing state"
            ) from error

    async def reindex_paper_by_id(self, paper_id: UUID) -> PaperReindexResult:
        """
        Rebuild Elasticsearch documents for every chunk owned by one paper.

        Returns:
            paper reindexing summary

        Raises:
            ElasticsearchPaperNotFoundError:
                if paper does not exist locally
            ElasticsearchIndexError:
                if Elasticsearch index setup fails
            ElasticsearchDeleteError:
                if deleting old indexed chunks fails
            ElasticsearchBulkIndexError:
                if Elasticsearch bulk indexing fails before per-chunk errors
                can be recorded
            ElasticsearchPersistenceError:
                if local indexing state persistence fails
        """
        try:
            paper = self.paper_repository.get_by_id(paper_id)

            if paper is None:
                raise ElasticsearchPaperNotFoundError(f"Paper not found: {paper_id}")

            self.elasticsearch_client.ensure_chunk_index()

            # delete chunks by paper in elasticsearch, as well as reset its status
            # on database
            self.elasticsearch_client.delete_chunks_by_paper(str(paper.id))
            chunks = self.chunk_repository.reset_indexing_by_paper(paper.id)

            eligible_chunks = [
                EligibleChunk(chunk=chunk, paper=paper) for chunk in chunks
            ]

            # start reindexing
            self.paper_repository.mark_indexing_started(paper)

            result = await self._index_chunks(eligible_chunks)

            if not chunks:
                self.paper_repository.mark_chunking_skipped(paper)
            elif result.failed_chunks:
                self.paper_repository.mark_indexing_failed(
                    paper,
                    f"{result.failed_chunks} chunk(s) failed embedding or indexing",
                )
            else:
                self.paper_repository.mark_indexed(paper)

            self.session.commit()

            return PaperReindexResult(
                embedding_model_name=result.embedding_model_name,
                requested_chunks=result.requested_chunks,
                indexed_chunks=result.indexed_chunks,
                failed_chunks=result.failed_chunks,
                errors=result.errors,
            )

        except ElasticsearchServiceError:
            self.session.rollback()
            raise

        except SQLAlchemyError as error:
            self.session.rollback()
            raise ElasticsearchPersistenceError(
                "Failed to persist paper reindexing state"
            ) from error

    async def _index_chunks(
        self,
        eligible_chunks: list[EligibleChunk],
    ) -> ChunkIndexingResult:
        """
        core chunk indexing operation

        Do not re-query chunks by embedding_status here. A chunk can already be
        EMBEDDED while its indexing_status is still PENDING, so querying only for
        pending embeddings would skip chunks that are ready to index.
        """
        documents: list[dict[str, Any]] = []  # documents to be inserted
        embedded_chunks: dict[str, ChunkModel] = {}  # successful embedded chunks buffer

        failed_count = 0
        errors_by_chunk_id: dict[UUID, str] = {}

        chunks = [eligible.chunk for eligible in eligible_chunks]

        # embed exactly the chunks we were handed, no re-query
        try:
            embedding_result: ChunkEmbeddingResult = (
                await self.chunk_embedding_service.embed_chunks(chunks)
            )

        except EmbeddingServiceError as error:
            for chunk in chunks:
                error_message = (
                    f"chunk {chunk.id} failed during embedding before indexing: "
                    f"{error}"
                )
                errors_by_chunk_id[chunk.id] = error_message

                self.chunk_repository.mark_embedding_failed(chunk, str(error))
                self.chunk_repository.mark_indexing_failed(chunk, error_message)

            return ChunkIndexingResult(
                embedding_model_name=self.embedding_model_name,
                requested_chunks=len(chunks),
                indexed_chunks=0,
                failed_chunks=len(chunks),
                errors=errors_by_chunk_id,
            )

        # embedding lookup by chunk id
        embeddings_by_chunk_id = embedding_result.embeddings_by_chunk_id

        failed_count += embedding_result.failed_chunks
        errors_by_chunk_id.update(embedding_result.errors)

        for eligible in eligible_chunks:
            # extract field
            chunk, paper = eligible.to_tuple

            # get embedding by chunk id
            embedding = embeddings_by_chunk_id.get(chunk.id)

            # this would easily skipped the chunk that is marked as missing embeddings
            # the flow is very vague, but this is the simplest way
            if embedding is None:
                error_message = errors_by_chunk_id.get(
                    chunk.id,
                    f"chunk {chunk.id} was not indexed because embedding is missing",
                )
                errors_by_chunk_id[chunk.id] = error_message

                if chunk.id not in embedding_result.errors:
                    failed_count += 1
                    self.chunk_repository.mark_embedding_failed(chunk, error_message)

                self.chunk_repository.mark_indexing_failed(chunk, error_message)
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

        for chunk in embedded_chunks.values():
            self.chunk_repository.mark_indexing_started(chunk)

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
                # failed to embed + failed to bulk insert =
                # a total of chunk processed in this function
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

    def _sync_paper_indexing_status(self, paper: PaperModel) -> None:
        chunks = self.chunk_repository.list_by_paper_id(paper.id)

        if not chunks:
            self.paper_repository.mark_chunking_skipped(paper)
            return

        failed_chunk_count = sum(
            1
            for chunk in chunks
            if chunk.embedding_status == ChunkEmbeddingStatus.FAILED
            or chunk.indexing_status == ChunkIndexingStatus.FAILED
        )

        if failed_chunk_count:
            self.paper_repository.mark_indexing_failed(
                paper,
                f"{failed_chunk_count} chunk(s) failed embedding or indexing",
            )
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

        the keys must have matched the retured properties by
        `create_chunk_index_mapping()` function
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
