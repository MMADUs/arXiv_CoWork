# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Literal

from rag.db.model import PaperModel
from rag.db.repository.chunk_repository import ChunkErrorSummary
from server.routes.papers.schema import (
    ChunkErrorResponse,
    CompactPaperResponse,
    FullPaperResponse,
    PaperArtifactsResponse,
    PaperErrorsResponse,
    PaperMetadataResponse,
    PaperStatusResponse,
    PaperTimestampsResponse,
)


def paper_response(
    paper: PaperModel,
    output: Literal["compact", "full"],
    chunk_errors: list[ChunkErrorSummary] | None = None,
) -> CompactPaperResponse | FullPaperResponse:
    if output == "full":
        return FullPaperResponse(
            paper_id=paper.id,
            arxiv_id=paper.arxiv_id,
            metadata=PaperMetadataResponse(
                version=paper.version,
                title=paper.title,
                authors=paper.authors,
                abstract=paper.abstract,
                categories=paper.categories,
                published_date=paper.published_date,
                pdf_url=paper.pdf_url,
                doi=paper.doi,
            ),
            artifacts=PaperArtifactsResponse(
                pdf_object_key=paper.pdf_object_key,
                parsed_json_object_key=paper.parsed_json_object_key,
                parser_name=paper.parser_name,
            ),
            status=PaperStatusResponse(
                ingestion_status=paper.ingestion_status,
                parser_status=paper.parser_status,
                chunking_status=paper.chunking_status,
                indexing_status=paper.indexing_status,
            ),
            errors=PaperErrorsResponse(
                pdf_download_error=paper.pdf_download_error,
                parser_error=paper.parser_error,
                chunking_error=paper.chunking_error,
                indexing_error=paper.indexing_error,
                chunk_errors=[
                    ChunkErrorResponse(
                        stage=error.stage,
                        message=error.message,
                        count=error.count,
                    )
                    for error in chunk_errors or []
                ],
            ),
            timestamps=PaperTimestampsResponse(
                created_at=paper.created_at,
                updated_at=paper.updated_at,
            ),
        )

    return CompactPaperResponse(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=paper.authors,
        categories=paper.categories,
        published_date=paper.published_date,
    )
