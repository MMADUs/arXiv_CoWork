# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from datetime import date
from typing import Literal

from rag.service.elasticsearch.config import ElasticsearchClient, SearchHit, SearchResult
from rag.service.elasticsearch.searching.query_builder import ElasticsearchQueryBuilder
from rag.service.embedding import QueryEmbeddingService, EmbeddingProvider


@dataclass(slots=True)
class SearchingServiceResult:
    query: str
    mode: str
    size: int
    offset: int
    total: int
    results: list[SearchHit]

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "mode": self.mode,
            "size": self.size,
            "offset": self.offset,
            "total": self.total,
            "results": [hit.to_dict() for hit in self.results],
        }


class SearchingService:
    RRF_K = 60
    hybrid_candidate_pool_size = 50

    def __init__(
        self,
        elasticsearch_client: ElasticsearchClient,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.elasticsearch_client = elasticsearch_client
        self.query_embedding_service = QueryEmbeddingService(embedding_provider)

    async def search(
        self,
        query: str,
        mode: Literal["bm25", "vector", "hybrid"],
        size: int = 10,
        offset: int = 0,
        candidate_pool_size: int | None = None,
        num_candidates: int | None = None,
        categories: list[str] | None = None,
        paper_id: str | None = None,
        published_from: date | None = None,
        published_to: date | None = None,
        latest_first: bool = False,
        min_score: float | None = None,
        track_total_hits: bool = True,
        fuzziness: str | None = None,
        include_highlights: bool = True,
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

        query_vector: list[float] | None = None

        if mode in ["vector", "hybrid"]:
            query_vector = await self.query_embedding_service.embed_query(query)

        # BM25
        if mode == "bm25":
            bm25_query = query_builder.bm25(
                query=query,
                size=size,
                offset=offset,
                latest_first=latest_first,
                fuzziness=fuzziness,
                include_highlights=include_highlights,
            )

            response = self.elasticsearch_client.search(body=bm25_query)

        # VECTOR
        elif mode == "vector":
            if query_vector is None:
                raise RuntimeError("query vector was not generated")

            vector_query = query_builder.vector(
                query_vector=query_vector,
                size=size,
                offset=offset,
                candidate_pool_size=candidate_pool_size,
                num_candidates=num_candidates,
            )

            response = self.elasticsearch_client.search(body=vector_query)

        # Hybrid RRF (BM25 + VECTOR), fused locally to avoid licensed ES RRF.
        elif mode == "hybrid":
            if query_vector is None:
                raise RuntimeError("query vector was not generated")

            candidate_size = self._candidate_size(
                size=size,
                offset=offset,
                candidate_pool_size=candidate_pool_size,
            )
            bm25_query = query_builder.bm25(
                query=query,
                size=candidate_size,
                offset=0,
                latest_first=latest_first,
                fuzziness=fuzziness,
                include_highlights=include_highlights,
            )
            vector_query = query_builder.vector(
                query_vector=query_vector,
                size=candidate_size,
                offset=0,
                candidate_pool_size=candidate_size,
                num_candidates=num_candidates,
            )

            bm25_response = self.elasticsearch_client.search(body=bm25_query)
            vector_response = self.elasticsearch_client.search(body=vector_query)

            fused_hits = self._fuse_rrf(
                bm25_hits=bm25_response.hits,
                vector_hits=vector_response.hits,
            )
            
            response = SearchResult(
                total=len(fused_hits),
                hits=fused_hits[offset : offset + size],
                raw_response={
                    "fusion": "local_rrf",
                    "bm25_total": bm25_response.total,
                    "vector_total": vector_response.total,
                },
            )

        else:
            raise ValueError(f"Unsupported search mode: {mode}")

        return SearchingServiceResult(
            query=query,
            mode=mode,
            size=size,
            offset=offset,
            total=response.total,
            results=response.hits,
        )

    def _candidate_size(
        self,
        size: int,
        offset: int,
        candidate_pool_size: int | None,
    ) -> int:
        minimum = size + offset

        if candidate_pool_size is not None:
            return candidate_pool_size

        return max(minimum, self.hybrid_candidate_pool_size)

    def _fuse_rrf(
        self,
        bm25_hits: list[SearchHit],
        vector_hits: list[SearchHit],
    ) -> list[SearchHit]:
        hits_by_chunk_id: dict[str, SearchHit] = {}
        scores_by_chunk_id: dict[str, float] = {}
        ranks_by_chunk_id: dict[str, dict[str, int]] = {}

        self._add_ranked_hits(
            hits=bm25_hits,
            rank_name="bm25_rank",
            hits_by_chunk_id=hits_by_chunk_id,
            scores_by_chunk_id=scores_by_chunk_id,
            ranks_by_chunk_id=ranks_by_chunk_id,
        )
        self._add_ranked_hits(
            hits=vector_hits,
            rank_name="vector_rank",
            hits_by_chunk_id=hits_by_chunk_id,
            scores_by_chunk_id=scores_by_chunk_id,
            ranks_by_chunk_id=ranks_by_chunk_id,
        )

        fused_hits: list[SearchHit] = []

        for chunk_id, hit in hits_by_chunk_id.items():
            source = {
                **hit.source,
                **ranks_by_chunk_id[chunk_id],
                "rrf_score": scores_by_chunk_id[chunk_id],
            }
            fused_hits.append(
                SearchHit(
                    id=hit.id,
                    score=scores_by_chunk_id[chunk_id],
                    source=source,
                    highlights=hit.highlights,
                )
            )

        return sorted(fused_hits, key=lambda hit: hit.score or 0.0, reverse=True)

    def _add_ranked_hits(
        self,
        hits: list[SearchHit],
        rank_name: str,
        hits_by_chunk_id: dict[str, SearchHit],
        scores_by_chunk_id: dict[str, float],
        ranks_by_chunk_id: dict[str, dict[str, int]],
    ) -> None:
        for rank, hit in enumerate(hits, start=1):
            chunk_id = hit.chunk_id

            if chunk_id not in hits_by_chunk_id:
                hits_by_chunk_id[chunk_id] = hit
                scores_by_chunk_id[chunk_id] = 0.0
                ranks_by_chunk_id[chunk_id] = {}
            elif rank_name == "bm25_rank" and hit.highlights:
                hits_by_chunk_id[chunk_id] = hit

            scores_by_chunk_id[chunk_id] += 1 / (self.RRF_K + rank)
            ranks_by_chunk_id[chunk_id][rank_name] = rank
