# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from rag.service.llm import LLMUsageMetadata
from rag.service.orchestration.context_builder import Citation, Source
from rag.service.orchestration.input_guardrails import InputGuardrailResult


ScopeDecisionName = Literal["retrieve", "direct_response", "out_of_scope"]
EvidenceGradeName = Literal["strong", "weak", "none"]
CritiqueVerdict = Literal["pass", "repair", "fail"]


@dataclass(frozen=True, slots=True)
class AgenticRAGRequest:
    question: str
    thread_id: str | None = None
    conversation_id: str | None = None
    current_message_id: str | None = None
    conversation_context: list[dict[str, Any]] = field(default_factory=list)
    retrieval_mode: Literal["bm25", "vector", "hybrid"] | None = None
    top_k: int | None = None
    candidate_pool_size: int | None = None
    use_reranker: bool | None = None
    num_candidates: int | None = None
    categories: list[str] | None = None
    paper_id: str | None = None
    published_from: str | None = None
    published_to: str | None = None
    latest_first: bool = False
    min_score: float | None = None
    track_total_hits: bool = True
    include_highlights: bool = False
    fuzziness: str | None = None


@dataclass(frozen=True, slots=True)
class AgenticRAGMetadata:
    thread_id: str
    conversation_id: str | None
    current_message_id: str | None
    resolved_query: str
    retrieval_used: bool
    guardrail: dict[str, Any]
    evidence_grade: dict[str, Any]
    rewritten_query: str | None
    answer_model: str | None
    answer_usage: LLMUsageMetadata | None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "conversation_id": self.conversation_id,
            "current_message_id": self.current_message_id,
            "resolved_query": self.resolved_query,
            "retrieval_used": self.retrieval_used,
            "guardrail": self.guardrail,
            "evidence_grade": self.evidence_grade,
            "rewritten_query": self.rewritten_query,
            "answer_model": self.answer_model,
            "answer_usage": (
                None if self.answer_usage is None else asdict(self.answer_usage)
            ),
            "errors": self.errors,
        }


@dataclass(frozen=True, slots=True)
class AgenticRAGResult:
    thread_id: str
    answer: str
    blocked: bool
    guardrail: InputGuardrailResult | None
    citations: list[Citation]
    sources: list[Source]
    metadata: AgenticRAGMetadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "answer": self.answer,
            "blocked": self.blocked,
            "guardrail": None if self.guardrail is None else self.guardrail.to_dict(),
            "citations": [citation.to_dict() for citation in self.citations],
            "sources": [source.to_dict() for source in self.sources],
            "metadata": self.metadata.to_dict(),
        }
