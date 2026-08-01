# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from abc import ABC, abstractmethod

from rag.service.elasticsearch.config import SearchHit


@dataclass(frozen=True)
class RerankCandidate:
    chunk_id: str
    chunk: SearchHit
    original_rank: int
    original_score: float | None
    reranker_score: float | None
    final_score: float | None
    final_rank: int

    def to_hit(self) -> SearchHit:
        source = {
            **self.chunk.source,
            "original_score": self.original_score,
            "original_rank": self.original_rank,
            "reranker_score": self.reranker_score,
            "final_score": self.final_score,
            "final_rank": self.final_rank,
        }

        return SearchHit(
            id=self.chunk.id,
            score=self.final_score,
            source=source,
            highlights=self.chunk.highlights,
        )


@dataclass(frozen=True)
class RerankResult:
    provider: str
    model_name: str
    reranked_candidates: list[RerankCandidate]
    latency_ms: float | None = None

    def hits(self) -> list[SearchHit]:
        return [candidate.to_hit() for candidate in self.reranked_candidates]

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "latency_ms": self.latency_ms,
            "results": [hit.to_dict() for hit in self.hits()],
            "reranked_candidates": [
                {
                    "chunk_id": candidate.chunk_id,
                    "original_rank": candidate.original_rank,
                    "original_score": candidate.original_score,
                    "reranker_score": candidate.reranker_score,
                    "final_score": candidate.final_score,
                    "final_rank": candidate.final_rank,
                    "chunk": candidate.to_hit().to_dict(),
                }
                for candidate in self.reranked_candidates
            ],
        }


class RerankerProvider(ABC):
    """
    Any reranker providers must inherit the `RerankerProvider` class
    """

    provider_name: str

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[SearchHit],
        top_k: int,
    ) -> RerankResult:
        """
        rerank searched chunks and return typed chunk candidates
        """
