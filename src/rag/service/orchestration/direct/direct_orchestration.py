# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from rag.service.elasticsearch.config import SearchHit
from rag.service.elasticsearch.searching import SearchingService
from rag.service.llm import LLMGenerationSettings, LLMProvider, LLMUsageMetadata
from rag.service.orchestration.direct.context_builder import Citation, ContextBuilder, Source
from rag.service.orchestration.direct.input_guardrails import (
    InputGuardrailResult,
    InputGuardrails,
)
from rag.service.orchestration.direct.prompt_builder import PromptBuilder
from rag.service.reranker.interface import RerankerProvider

RetrievalMode = Literal["bm25", "vector", "hybrid"]


@dataclass(frozen=True, slots=True)
class DirectRagRequest:
    question: str
    retrieval_mode: RetrievalMode = "hybrid"
    top_k: int = 8
    candidate_pool_size: int = 50
    use_reranker: bool = False
    num_candidates: int | None = None
    categories: list[str] | None = None
    paper_id: str | None = None
    published_from: date | None = None
    published_to: date | None = None
    latest_first: bool = False
    min_score: float | None = None
    track_total_hits: bool = True
    include_highlights: bool = False
    fuzziness: str | None = None

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("top_k must be greater than 0")

        if self.candidate_pool_size < self.top_k:
            raise ValueError(
                "candidate_pool_size must be greater than or equal to top_k"
            )

        if self.num_candidates is not None and self.num_candidates < 1:
            raise ValueError("num_candidates must be greater than 0")

        if (
            self.published_from is not None
            and self.published_to is not None
            and self.published_from > self.published_to
        ):
            raise ValueError("published_from must be before or equal to published_to")


@dataclass(frozen=True, slots=True)
class DirectRagMetadata:
    retrieval_mode: RetrievalMode
    use_reranker: bool
    search_candidates: int
    context_chunks: int
    total_hits: int
    guardrail_risk_level: str
    guardrail_categories: list[str]
    answer_model: str | None
    answer_usage: LLMUsageMetadata | None
    reranker_model: str | None = None
    reranker_latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_mode": self.retrieval_mode,
            "use_reranker": self.use_reranker,
            "search_candidates": self.search_candidates,
            "context_chunks": self.context_chunks,
            "total_hits": self.total_hits,
            "guardrail_risk_level": self.guardrail_risk_level,
            "guardrail_categories": self.guardrail_categories,
            "answer_model": self.answer_model,
            "answer_usage": (
                None if self.answer_usage is None else asdict(self.answer_usage)
            ),
            "reranker_model": self.reranker_model,
            "reranker_latency_ms": self.reranker_latency_ms,
        }


@dataclass(frozen=True, slots=True)
class DirectRagResult:
    answer: str
    blocked: bool
    guardrail: InputGuardrailResult
    citations: list[Citation]
    sources: list[Source]
    metadata: DirectRagMetadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "blocked": self.blocked,
            "guardrail": self.guardrail.to_dict(),
            "citations": [citation.to_dict() for citation in self.citations],
            "sources": [source.to_dict() for source in self.sources],
            "metadata": self.metadata.to_dict(),
        }


class DirectRagOrchestrator:
    def __init__(
        self,
        searching_service: SearchingService,
        llm_provider: LLMProvider,
        reranker_provider: RerankerProvider | None = None,
        input_guardrails: InputGuardrails | None = None,
        context_builder: ContextBuilder | None = None,
        prompt_builder: PromptBuilder | None = None,
        answer_settings: LLMGenerationSettings | None = None,
    ) -> None:
        self.searching_service = searching_service
        self.llm_provider = llm_provider
        self.reranker_provider = reranker_provider
        self.input_guardrails = input_guardrails or InputGuardrails(llm_provider)
        self.context_builder = context_builder or ContextBuilder()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.answer_settings = answer_settings or LLMGenerationSettings()

    async def answer(self, request: DirectRagRequest) -> DirectRagResult:
        guardrail = await self.input_guardrails.evaluate(request.question)

        if not guardrail.allowed:
            return self._blocked_result(
                request=request,
                guardrail=guardrail,
            )

        assert guardrail.safe_query is not None

        search_size = (
            request.candidate_pool_size if request.use_reranker else request.top_k
        )

        search_result = await self.searching_service.search(
            query=guardrail.safe_query,
            mode=request.retrieval_mode,
            size=search_size,
            offset=0,
            candidate_pool_size=(
                request.candidate_pool_size if request.use_reranker else None
            ),
            num_candidates=request.num_candidates,
            categories=request.categories,
            paper_id=request.paper_id,
            published_from=request.published_from,
            published_to=request.published_to,
            latest_first=request.latest_first,
            min_score=request.min_score,
            track_total_hits=request.track_total_hits,
            fuzziness=request.fuzziness,
            include_highlights=request.include_highlights,
        )

        hits = search_result.results
        reranker_model: str | None = None
        reranker_latency_ms: float | None = None

        if request.use_reranker:
            if self.reranker_provider is None:
                raise RuntimeError(
                    "reranker_provider is required when use_reranker is true"
                )

            rerank_result = await self.reranker_provider.rerank(
                query=guardrail.safe_query,
                chunks=hits,
                top_k=request.top_k,
            )

            hits = rerank_result.hits()
            reranker_model = rerank_result.model_name
            reranker_latency_ms = rerank_result.latency_ms

        context = self.context_builder.build(self._limit_hits(hits, request.top_k))
        built_prompt = self.prompt_builder.build(
            question=guardrail.safe_query,
            context=context,
        )
        generation = await self.llm_provider.generate(
            prompt=built_prompt.prompt,
            settings=self.answer_settings,
        )

        return DirectRagResult(
            answer=generation.text,
            blocked=False,
            guardrail=guardrail,
            citations=context.citations,
            sources=context.sources,
            metadata=DirectRagMetadata(
                retrieval_mode=request.retrieval_mode,
                use_reranker=request.use_reranker,
                search_candidates=len(search_result.results),
                context_chunks=context.chunk_count,
                total_hits=search_result.total,
                guardrail_risk_level=guardrail.risk_level,
                guardrail_categories=guardrail.categories,
                answer_model=generation.model_name,
                answer_usage=generation.usage,
                reranker_model=reranker_model,
                reranker_latency_ms=reranker_latency_ms,
            ),
        )

    def _blocked_result(
        self,
        request: DirectRagRequest,
        guardrail: InputGuardrailResult,
    ) -> DirectRagResult:
        return DirectRagResult(
            answer=guardrail.response or "Sorry, I can't process that request.",
            blocked=True,
            guardrail=guardrail,
            citations=[],
            sources=[],
            metadata=DirectRagMetadata(
                retrieval_mode=request.retrieval_mode,
                use_reranker=request.use_reranker,
                search_candidates=0,
                context_chunks=0,
                total_hits=0,
                guardrail_risk_level=guardrail.risk_level,
                guardrail_categories=guardrail.categories,
                answer_model=None,
                answer_usage=None,
            ),
        )

    def _limit_hits(self, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        return hits[:top_k]
