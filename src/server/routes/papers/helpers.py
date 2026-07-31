# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Literal

from rag.db.model import PaperModel
from server.routes.papers.schema import CompactPaperResponse, FullPaperResponse


def paper_response(
    paper: PaperModel,
    output: Literal["compact", "full"],
) -> CompactPaperResponse | FullPaperResponse:
    if output == "full":
        return FullPaperResponse(
            paper_id=paper.id,
            arxiv_id=paper.arxiv_id,
            version=paper.version,
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            categories=paper.categories,
            published_date=paper.published_date,
            pdf_url=paper.pdf_url,
            doi=paper.doi,
            pdf_object_key=paper.pdf_object_key,
            parsed_json_object_key=paper.parsed_json_object_key,
            parser_name=paper.parser_name,
            parser_error=paper.parser_error,
            ingestion_status=paper.ingestion_status,
            parser_status=paper.parser_status,
            indexing_status=paper.indexing_status,
            created_at=paper.created_at,
            updated_at=paper.updated_at,
        )

    return CompactPaperResponse(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=paper.authors,
        categories=paper.categories,
        published_date=paper.published_date,
    )
