# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from rag.config import AgenticRAGSettings
from rag.service.elasticsearch.searching import SearchingService
from rag.service.llm import LLMProvider, LLMUsageMetadata
from rag.service.orchestration.agentic.graph import build_agentic_rag_graph
from rag.service.orchestration.agentic.nodes import AgenticRAGNodes
from rag.service.orchestration.agentic.schemas import (
    AgenticRAGMetadata,
    AgenticRAGRequest,
    AgenticRAGResult,
)
from rag.service.orchestration.agentic.state import AgenticRAGState
from rag.service.orchestration.direct import Citation, InputGuardrailResult, Source
from rag.service.reranker import RerankerProvider

_MEMORY_CHECKPOINTER = InMemorySaver()


class AgenticRAGOrchestrator:
    def __init__(
        self,
        settings: AgenticRAGSettings,
        searching_service: SearchingService,
        llm_provider: LLMProvider,
        reranker_provider: RerankerProvider | None = None,
    ) -> None:
        self.settings = settings
        self.nodes = AgenticRAGNodes(
            settings=settings,
            searching_service=searching_service,
            llm_provider=llm_provider,
            reranker_provider=reranker_provider,
        )
        checkpointer = (
            _MEMORY_CHECKPOINTER if settings.checkpoint_provider == "memory" else None
        )
        self.graph = build_agentic_rag_graph(self.nodes, checkpointer=checkpointer)

    async def answer(self, request: AgenticRAGRequest) -> AgenticRAGResult:
        thread_id = request.thread_id or str(uuid4())

        input_state = self._make_input_state(request, thread_id)
        config = {
            "configurable": {
                "thread_id": thread_id,
            },
        }

        final_state = await self.graph.ainvoke(input_state, config=config)

        return self._make_result(final_state)

    def _make_input_state(
        self,
        request: AgenticRAGRequest,
        thread_id: str,
    ) -> AgenticRAGState:
        return {
            "thread_id": thread_id,
            "question": request.question,
            "retrieval_mode": request.retrieval_mode or "hybrid",
            "top_k": request.top_k or self.settings.default_top_k,
            "candidate_pool_size": (
                request.candidate_pool_size or self.settings.default_candidate_pool_size
            ),
            "use_reranker": (
                request.use_reranker
                if request.use_reranker is not None
                else self.settings.use_reranker_by_default
            ),
            "num_candidates": request.num_candidates,
            "categories": request.categories,
            "paper_id": request.paper_id,
            "published_from": request.published_from,
            "published_to": request.published_to,
            "latest_first": request.latest_first,
            "min_score": request.min_score,
            "track_total_hits": request.track_total_hits,
            "include_highlights": request.include_highlights,
            "fuzziness": request.fuzziness,
            "max_retrieval_attempts": self.settings.max_retrieval_attempts,
            "max_answer_repair_attempts": self.settings.max_answer_repair_attempts,
            "enable_query_rewrite": self.settings.enable_query_rewrite,
            "enable_answer_repair": self.settings.enable_answer_repair,
            "enable_post_answer_retrieval": (
                self.settings.enable_post_answer_retrieval
            ),
        }

    def _make_result(self, state: AgenticRAGState) -> AgenticRAGResult:
        guardrail = self._guardrail_from_state(state.get("guardrail"))
        metadata = state.get("metadata", {})

        return AgenticRAGResult(
            thread_id=state["thread_id"],
            answer=state.get("answer", ""),
            blocked=bool(state.get("blocked", False)),
            guardrail=guardrail,
            citations=[
                self._citation_from_state(citation)
                for citation in state.get("citations", [])
            ],
            sources=[
                self._source_from_state(source) for source in state.get("sources", [])
            ],
            metadata=AgenticRAGMetadata(
                thread_id=state["thread_id"],
                retrieval_attempts=int(state.get("retrieval_attempts", 0)),
                answer_repair_attempts=int(state.get("answer_repair_attempts", 0)),
                reasoning_steps=state.get("reasoning_steps", []),
                guardrail=state.get("guardrail", {}),
                scope=state.get("scope", {}),
                followup=state.get("followup", {}),
                retrieval_plan=state.get("retrieval_plan", {}),
                evidence_grade=state.get("evidence_grade", {}),
                citation_verification=state.get("citation_verification", {}),
                answer_critique=state.get("answer_critique", {}),
                rewritten_query=state.get("rewritten_query"),
                answer_model=metadata.get("answer_model"),
                answer_usage=self._usage_from_state(metadata.get("answer_usage")),
                errors=state.get("errors", []),
            ),
        )

    def _guardrail_from_state(
        self,
        data: dict[str, Any] | None,
    ) -> InputGuardrailResult | None:
        if not data:
            return None

        return InputGuardrailResult(
            decision=data["decision"],
            risk_level=data["risk_level"],
            categories=[str(value) for value in data.get("categories", [])],
            reason=data.get("reason"),
            safe_query=data.get("safe_query"),
            response=data.get("response"),
            raw_response=dict(data.get("raw_response", {})),
        )

    def _citation_from_state(self, data: dict[str, Any]) -> Citation:
        return Citation(
            source_number=int(data["source_number"]),
            chunk_id=str(data["chunk_id"]),
            paper_id=str(data["paper_id"]),
            arxiv_id=str(data["arxiv_id"]),
            title=str(data["title"]),
            section_title=data.get("section_title"),
            pdf_url=str(data["pdf_url"]),
            chunk_index=int(data["chunk_index"]),
            start_word=int(data["start_word"]),
            end_word=int(data["end_word"]),
            start_char=int(data["start_char"]),
            end_char=int(data["end_char"]),
            score=data.get("score"),
            highlights=[str(value) for value in data.get("highlights", [])],
        )

    def _source_from_state(self, data: dict[str, Any]) -> Source:
        return Source(
            paper_source_number=int(data["paper_source_number"]),
            paper_id=str(data["paper_id"]),
            arxiv_id=str(data["arxiv_id"]),
            title=str(data["title"]),
            authors=[str(value) for value in data.get("authors", [])],
            categories=[str(value) for value in data.get("categories", [])],
            published_date=str(data["published_date"]),
            pdf_url=str(data["pdf_url"]),
            pdf_storage_key=data.get("pdf_storage_key"),
            citation_numbers=[int(value) for value in data.get("citation_numbers", [])],
        )

    def _usage_from_state(self, value: Any) -> LLMUsageMetadata | None:
        if value is None:
            return None

        if isinstance(value, LLMUsageMetadata):
            return value

        if not isinstance(value, dict):
            return None

        return LLMUsageMetadata(
            prompt_tokens=int(value.get("prompt_tokens", 0)),
            completion_tokens=int(value.get("completion_tokens", 0)),
            total_tokens=int(value.get("total_tokens", 0)),
            prompt_eval_duration_ms=float(value.get("prompt_eval_duration_ms", 0.0)),
            eval_duration_ms=float(value.get("eval_duration_ms", 0.0)),
            load_duration_ms=float(value.get("load_duration_ms", 0.0)),
            latency_ms=float(value.get("latency_ms", 0.0)),
        )
