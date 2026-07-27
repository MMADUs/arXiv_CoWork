# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID
from dataclasses import dataclass
from typing import Any

from typing import Any
from abc import ABC, abstractmethod


@dataclass(frozen=True)
class RerankCandidate:
    chunk_id: UUID # idk should be uuid or str
    chunk: dict[str, Any]
    original_rank: int
    original_score: float | None
    reranker_score: float | None
    final_rank: int


@dataclass(frozen=True)
class RerankResult:
    provider: str
    model_name: str
    latency_ms: float | None = None
    reranked_candidates: list[RerankCandidate]


class RerankerProvider(ABC):
    """
    Any reranker providers must inherit the `RerankerProvider` class
    """

    provider_name: str

    @abstractmethod
    def rerank(self) -> None:
        """
        inspect bucket if exist, otherwise create new bucket
        """
