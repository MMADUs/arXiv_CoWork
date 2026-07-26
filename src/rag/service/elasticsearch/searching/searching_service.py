# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from datetime import date
from typing import Literal, Any

from rag.service.elasticsearch.config import ElasticsearchClient, ESRawJsonResponse
from rag.service.elasticsearch.searching.query_builder import ElasticsearchQueryBuilder
from rag.service.embedding import QueryEmbeddingService, EmbeddingProvider


@dataclass(slots=True)
class SearchingServiceResult:
    query: str
    mode: str
    size: int
    offset: int
    total: int
    results: ESRawJsonResponse


class SearchingService:
    RRF_K = 60
    hybrid_candidate_pool_size = 50

    def __init__(
        self,
        elasticsearch_client: ElasticsearchClient,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.elasticsearch_client = elasticsearch_client
        self.query_embedding_servcie = QueryEmbeddingService(embedding_provider)

    async def search(
        self,
        query: str,
        mode: Literal["bm25", "vector", "hybrid"],
        size: int = 10,
        offset: int = 0,
        categories: list[str] | None = None,
        paper_id: str | None = None,
        published_from: date | None = None,
        published_to: date | None = None,
        latest_first: bool = False,
        min_score: float | None = None,
        track_total_hits: bool = True,
    ) -> SearchingServiceResult:
        # main query builder
        query_builder = ElasticsearchQueryBuilder(
            categories=categories,
            paper_id=paper_id,
            published_from=published_from,
            published_to=published_to,
            min_score=min_score,
            track_total_hits=track_total_hits,
        )

        # only generate query embeddings when mode is either `bm25` or `hybrid`
        if mode in ["bm25", "hybrid"]:
            query_vector = await self.query_embedding_servcie.embed_query(query)

        # final search response
        response: dict[str, Any] = {}

        # BM25
        if mode == "bm25":
            bm25_query = query_builder.bm25(
                query=query,
                size=size,
                offset=offset,
                latest_first=latest_first,
            )

            data = self.elasticsearch_client.search(body=bm25_query)
            response = self._parse_search_response(data)

        # VECTOR
        elif mode == "vector":
            vector_query = query_builder.vector(
                query_vector=query_vector,
                size=size,
                offset=offset,
            )

            data = self.elasticsearch_client.search(body=vector_query)
            response = self._parse_search_response(data)

        # Hybrid RRF (BM25 + VECTOR)
        elif mode == "hybrid":
            hybrid_query = query_builder.hybrid_rrf(
                query=query,
                query_vector=query_vector,
                size=size,
                offset=offset,
                rank_window_size=self._candidate_size(size=size, offset=offset),
                rank_constant=self.RRF_K,
            )

            data = self.elasticsearch_client.search(body=hybrid_query)
            response = self._parse_search_response(data)

        else:
            raise ValueError(f"Unsupported search mode: {mode}")

        return SearchingServiceResult(
            query=query,
            mode=mode,
            size=size,
            offset=offset,
            total=int(response["total"]),
            results=response["items"],
        )

    def _candidate_size(self, size: int, offset: int) -> int:
        return max(size + offset, self.hybrid_candidate_pool_size)

    def _parse_search_response(self, data: dict[str, Any]) -> dict[str, Any]:
        hits = data["hits"]
        total = hits["total"]

        if isinstance(total, dict):
            total_value = total["value"]
        else:
            total_value = total

        return {
            "total": total_value,
            "items": [self._make_search_item(hit) for hit in hits["hits"]],
        }

    def _make_search_item(self, hit: dict[str, Any]) -> dict[str, Any]:
        source = hit["_source"]
        highlights = []

        for snippets in hit.get("highlight", {}).values():
            highlights.extend(snippets)

        return {
            "score": hit["_score"],
            "highlights": highlights,
            **source,
        }
