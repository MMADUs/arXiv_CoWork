# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from rag.service.embedding import (
    EmbeddingNonRetryableError,
    EmbeddingRetryableError,
    EmbeddingServiceError,
    EmbeddingValidationError,
)
from rag.service.elasticsearch import (
    ElasticsearchNonRetryableError,
    ElasticsearchRetryableError,
    ElasticsearchServiceError,
)
from rag.service.elasticsearch.config import SearchHit
from rag.service.elasticsearch.searching import SearchingService
from rag.service.llm import (
    LLMGenerationSettings,
    LLMNonRetryableError,
    LLMProvider,
    LLMRetryableError,
    LLMServiceError,
    LLMUsageMetadata,
    LLMValidationError,
)
from rag.service.orchestration.context_builder import (
    Citation,
    ContextBuilder,
    Source,
)
from rag.service.orchestration.core.direct.direct_exceptions import (
    DirectRagNonRetryableError,
    DirectRagRetryableError,
    DirectRagServiceError,
    DirectRagValidationError,
)
from rag.service.orchestration.input_guardrails import (
    InputGuardrailError,
    InputGuardrailResult,
    InputGuardrails,
)
from rag.service.orchestration.prompt_builder import (
    PromptBuilder,
    QuestionValidationError,
)
from rag.service.reranker import (
    RerankerNonRetryableError,
    RerankerRetryableError,
    RerankerServiceError,
    RerankerValidationError,
)
from rag.service.reranker.reranker_interface import RerankerProvider

RetrievalMode = Literal["bm25", "vector", "hybrid"]


@dataclass(frozen=True, slots=True)
class DirectRagRequest:
    """
    Request payload for direct ask RAG orchestrator
    """

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
            raise DirectRagValidationError("top_k must be greater than 0")

        if self.candidate_pool_size < self.top_k:
            raise DirectRagValidationError(
                "candidate_pool_size must be greater than or equal to top_k"
            )

        if self.num_candidates is not None and self.num_candidates < 1:
            raise DirectRagValidationError("num_candidates must be greater than 0")

        if (
            self.published_from is not None
            and self.published_to is not None
            and self.published_from > self.published_to
        ):
            raise DirectRagValidationError(
                "published_from must be before or equal to published_to"
            )


@dataclass(frozen=True, slots=True)
class DirectRagMetadata:
    """
    Response schema for direct RAG orchestration metadata,
    useful for debugging why retrieval and answer in a certain result
    """

    retrieval_mode: RetrievalMode
    use_reranker: bool
    total_hits: int
    answer_model: str | None
    answer_usage: LLMUsageMetadata | None
    reranker_model: str | None = None
    reranker_latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_mode": self.retrieval_mode,
            "use_reranker": self.use_reranker,
            "total_hits": self.total_hits,
            "answer_model": self.answer_model,
            "answer_usage": (
                None if self.answer_usage is None else asdict(self.answer_usage)
            ),
            "reranker_model": self.reranker_model,
            "reranker_latency_ms": self.reranker_latency_ms,
        }


@dataclass(frozen=True, slots=True)
class DirectRagResult:
    """
    Response schema from direct RAG orchestrator,
    includes: answer, source with citations, and usage metadata
    """

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
    """
    Coordinates the direct RAG flow from validation through answer generation.

    The orchestrator owns the service boundary for direct ask: it evaluates
    guardrails, retrieves chunks, optionally reranks them, builds context and
    prompts, and translates downstream failures into direct RAG exceptions.
    """

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
        """
        Answer a direct RAG request using retrieved paper chunks.

        Returns a blocked result when input guardrails reject the question.
        Otherwise, retrieval and generation failures are translated into
        DirectRagServiceError subclasses for the caller to map to transport
        concerns such as HTTP status codes.

        Raises:
            DirectRagValidationError:
                If request values, retrieved context, prompt input, or reranker
                configuration are invalid.
            DirectRagRetryableError:
                If a downstream dependency fails in a way that may recover.
            DirectRagNonRetryableError:
                If a downstream dependency returns invalid or unsupported data.
            DirectRagServiceError:
                If orchestration fails outside the more specific categories.
        """

        try:
            guardrail = await self.input_guardrails.evaluate_user_query(
                request.question
            )

        except InputGuardrailError as error:
            raise DirectRagServiceError(
                f"Direct RAG guardrail evaluation failed: {error}"
            ) from error

        except LLMServiceError as error:
            raise self._llm_error(error, "guardrail evaluation") from error

        if not guardrail.allowed:
            return self._blocked_result(
                request=request,
                guardrail=guardrail,
            )

        assert guardrail.safe_query is not None

        search_size = (
            request.candidate_pool_size if request.use_reranker else request.top_k
        )

        try:
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

        except EmbeddingServiceError as error:
            raise self._embedding_error(error) from error

        except ElasticsearchServiceError as error:
            raise self._elasticsearch_error(error) from error

        except ValueError as error:
            raise DirectRagValidationError(
                f"Direct RAG search request is invalid: {error}"
            ) from error

        except RuntimeError as error:
            raise DirectRagServiceError(f"Direct RAG search failed: {error}") from error

        hits = search_result.results

        reranker_model: str | None = None
        reranker_latency_ms: float | None = None

        if request.use_reranker:
            if self.reranker_provider is None:
                raise DirectRagRetryableError(
                    "reranker_provider is required when use_reranker is true"
                )

            try:
                rerank_result = await self.reranker_provider.rerank(
                    query=guardrail.safe_query,
                    chunks=hits,
                    top_k=request.top_k,
                )

            except RerankerServiceError as error:
                raise self._reranker_error(error) from error

            hits = rerank_result.hits()
            reranker_model = rerank_result.model_name
            reranker_latency_ms = rerank_result.latency_ms

        try:
            context = self.context_builder.build_context(
                self._limit_hits(hits, request.top_k)
            )

        except (TypeError, ValueError) as error:
            raise DirectRagNonRetryableError(
                f"Direct RAG context build failed: {error}"
            ) from error

        try:
            built_prompt = self.prompt_builder.build_prompt(
                question=guardrail.safe_query,
                context=context,
            )

        except QuestionValidationError as error:
            raise DirectRagValidationError(
                f"Direct RAG prompt question is invalid: {error}"
            ) from error

        try:
            generation = await self.llm_provider.generate(
                prompt=built_prompt.prompt,
                settings=self.answer_settings,
            )

        except LLMServiceError as error:
            raise self._llm_error(error, "answer generation") from error

        return DirectRagResult(
            answer=generation.response_text,
            blocked=False,
            guardrail=guardrail,
            citations=context.citations,
            sources=context.sources,
            metadata=DirectRagMetadata(
                retrieval_mode=request.retrieval_mode,
                use_reranker=request.use_reranker,
                total_hits=search_result.total,
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
                total_hits=0,
                answer_model=None,
                answer_usage=None,
            ),
        )

    def _limit_hits(self, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        return hits[:top_k]

    def _embedding_error(self, error: EmbeddingServiceError) -> DirectRagServiceError:
        message = f"Direct RAG query embedding failed: {error}"

        if isinstance(error, EmbeddingValidationError):
            return DirectRagValidationError(message)

        if isinstance(error, EmbeddingNonRetryableError):
            return DirectRagNonRetryableError(message)

        if isinstance(error, EmbeddingRetryableError):
            return DirectRagRetryableError(message)

        return DirectRagServiceError(message)

    def _elasticsearch_error(
        self, error: ElasticsearchServiceError
    ) -> DirectRagServiceError:
        message = f"Direct RAG search backend failed: {error}"

        if isinstance(error, ElasticsearchNonRetryableError):
            return DirectRagNonRetryableError(message)

        if isinstance(error, ElasticsearchRetryableError):
            return DirectRagRetryableError(message)

        return DirectRagServiceError(message)

    def _reranker_error(self, error: RerankerServiceError) -> DirectRagServiceError:
        message = f"Direct RAG reranking failed: {error}"

        if isinstance(error, RerankerValidationError):
            return DirectRagValidationError(message)

        if isinstance(error, RerankerNonRetryableError):
            return DirectRagNonRetryableError(message)

        if isinstance(error, RerankerRetryableError):
            return DirectRagRetryableError(message)

        return DirectRagServiceError(message)

    def _llm_error(
        self, error: LLMServiceError, operation: str
    ) -> DirectRagServiceError:
        message = f"Direct RAG {operation} failed: {error}"

        if isinstance(error, LLMValidationError):
            return DirectRagValidationError(message)

        if isinstance(error, LLMNonRetryableError):
            return DirectRagNonRetryableError(message)

        if isinstance(error, LLMRetryableError):
            return DirectRagRetryableError(message)

        return DirectRagServiceError(message)
