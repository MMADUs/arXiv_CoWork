# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any, Literal, TypedDict

from rag.service.elasticsearch.config import SearchHit


AgenticRoute = Literal[
    "retrieve",
    "direct_response",
    "out_of_scope",
    "use_active_context",
    "no_context_fallback",
    "rewrite_query",
    "answer",
    "repair_answer",
    "targeted_retrieval",
    "save_thread_state",
    "blocked",
]


class AgenticRAGState(TypedDict, total=False):
    thread_id: str
    question: str
    safe_query: str
    current_query: str
    original_query: str
    rewritten_query: str | None

    retrieval_mode: Literal["bm25", "vector", "hybrid"]
    top_k: int
    candidate_pool_size: int
    use_reranker: bool
    num_candidates: int | None
    categories: list[str] | None
    paper_id: str | None
    published_from: str | None
    published_to: str | None
    latest_first: bool
    min_score: float | None
    track_total_hits: bool
    include_highlights: bool
    fuzziness: str | None

    blocked: bool
    answer: str
    guardrail: dict[str, Any]
    scope: dict[str, Any]
    followup: dict[str, Any]
    retrieval_plan: dict[str, Any]
    evidence_grade: dict[str, Any]
    citation_verification: dict[str, Any]
    answer_critique: dict[str, Any]

    search_hits: list[dict[str, Any]]
    reranked_hits: list[dict[str, Any]]
    active_hits: list[dict[str, Any]]
    active_chunk_ids: list[str]
    active_paper_ids: list[str]
    active_context_summary: str | None
    context: dict[str, Any]
    citations: list[dict[str, Any]]
    sources: list[dict[str, Any]]

    retrieval_attempts: int
    answer_repair_attempts: int
    max_retrieval_attempts: int
    max_answer_repair_attempts: int
    enable_query_rewrite: bool
    enable_answer_repair: bool
    enable_post_answer_retrieval: bool
    reasoning_steps: list[dict[str, Any]]
    errors: list[str]
    metadata: dict[str, Any]


def hit_to_state(hit: SearchHit) -> dict[str, Any]:
    return {
        "id": hit.id,
        "score": hit.score,
        "source": hit.source,
        "highlights": hit.highlights,
    }


def hit_from_state(data: dict[str, Any]) -> SearchHit:
    return SearchHit(
        id=str(data.get("id", data.get("elasticsearch_document_id", ""))),
        score=data.get("score"),
        source=dict(data.get("source", {})),
        highlights=[str(value) for value in data.get("highlights", [])],
    )


def hits_from_state(values: list[dict[str, Any]]) -> list[SearchHit]:
    return [hit_from_state(value) for value in values]


def hits_to_state(hits: list[SearchHit]) -> list[dict[str, Any]]:
    return [hit_to_state(hit) for hit in hits]


def append_step(
    state: AgenticRAGState,
    name: str,
    detail: dict[str, Any],
) -> list[dict[str, Any]]:
    steps = list(state.get("reasoning_steps", []))
    steps.append({"step": name, **detail})
    return steps
