# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from sqlalchemy.orm import Session

from rag.db.model import (
    PaperChunkingStatus,
    PaperIndexingStatus,
    PaperIngestionStatus,
    PaperModel,
    PaperParserStatus,
)
from rag.db.repository import ChunkRepository, PaperRepository
from rag.service.elasticsearch.config.client import ElasticsearchClient
from rag.service.storage import StorageProvider
from server.routes.removal.removal_schema import (
    DeletePaperIndexResponse,
    DeletePaperMetadataResponse,
)


class PaperRemovalNotFoundError(RuntimeError):
    """
    Paper not found error during removal
    """

    pass


class PaperRemovalConflictError(RuntimeError):
    """
    Paper not found error during removal
    """

    pass


def delete_paper_metadata(
    paper_id: UUID,
    session: Session,
    storage: StorageProvider,
) -> DeletePaperMetadataResponse:
    paper_repository = PaperRepository(session)
    chunk_repository = ChunkRepository(session)

    paper = paper_repository.get_by_id_for_update(paper_id)

    if paper is None:
        raise PaperRemovalNotFoundError(f"Paper not found: {paper_id}")

    _raise_if_metadata_removal_is_unsafe(paper)

    chunk_count = chunk_repository.count_by_paper_id(paper_id)

    if chunk_count:
        raise PaperRemovalConflictError(
            f"Delete paper index before deleting metadata: {paper_id}"
        )

    pdf_object_key = paper.pdf_object_key
    parsed_json_object_key = paper.parsed_json_object_key

    response = DeletePaperMetadataResponse(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        deleted_metadata=True,
        deleted_pdf=pdf_object_key is not None,
        deleted_parsed_json=parsed_json_object_key is not None,
        status="metadata_deleted",
    )

    if pdf_object_key is not None:
        storage.delete_file(pdf_object_key)

    if parsed_json_object_key is not None:
        storage.delete_file(parsed_json_object_key)

    paper_repository.delete(paper)

    session.commit()

    return response


def delete_paper_index(
    paper_id: UUID,
    session: Session,
    elasticsearch_client: ElasticsearchClient,
) -> DeletePaperIndexResponse:
    paper_repository = PaperRepository(session)
    chunk_repository = ChunkRepository(session)

    paper = paper_repository.get_by_id_for_update(paper_id)

    if paper is None:
        raise PaperRemovalNotFoundError(f"Paper not found: {paper_id}")

    _raise_if_index_removal_is_unsafe(paper)

    elasticsearch_delete_result = elasticsearch_client.delete_chunks_by_paper(
        str(paper.id)
    )

    if elasticsearch_delete_result.failures:
        raise RuntimeError(
            f"Failed to delete all Elasticsearch chunk documents: {paper_id}"
        )

    deleted_chunks = chunk_repository.delete_by_paper_id(paper_id)
    paper_repository.mark_chunks_removed(paper)
    
    session.commit()

    return DeletePaperIndexResponse(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        deleted_postgres_chunks=deleted_chunks,
        deleted_elasticsearch_documents=elasticsearch_delete_result.deleted,
        elasticsearch_index_exists=elasticsearch_delete_result.exists,
        elasticsearch_version_conflicts=elasticsearch_delete_result.version_conflicts,
        elasticsearch_failures=elasticsearch_delete_result.failures or [],
        status="index_deleted",
    )


def _raise_if_metadata_removal_is_unsafe(paper: PaperModel) -> None:
    if paper.ingestion_status == PaperIngestionStatus.PDF_DOWNLOADING:
        raise PaperRemovalConflictError(
            f"Paper PDF download is already in progress: {paper.id}"
        )

    _raise_if_index_removal_is_unsafe(paper)


def _raise_if_index_removal_is_unsafe(paper: PaperModel) -> None:
    if paper.parser_status == PaperParserStatus.PARSING:
        raise PaperRemovalConflictError(
            f"Paper parsing is already in progress: {paper.id}"
        )

    if paper.chunking_status == PaperChunkingStatus.CHUNKING:
        raise PaperRemovalConflictError(
            f"Paper chunking is already in progress: {paper.id}"
        )

    if paper.indexing_status == PaperIndexingStatus.INDEXING:
        raise PaperRemovalConflictError(
            f"Paper indexing is already in progress: {paper.id}"
        )
