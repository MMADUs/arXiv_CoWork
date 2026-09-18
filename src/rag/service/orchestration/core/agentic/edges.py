# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.service.orchestration.core.agentic.state import AgenticRAGState


def route_after_guardrail(state: AgenticRAGState) -> str:
    if state.get("blocked"):
        return "save_thread_state"

    return "scope_router"


def route_after_scope(state: AgenticRAGState) -> str:
    decision = state.get("scope", {}).get("decision")

    if decision in {"direct_response", "out_of_scope"}:
        return "save_thread_state"

    return "retrieve"


def route_after_evidence(state: AgenticRAGState) -> str:
    grade = state.get("evidence_grade", {}).get("grade")
    attempts = int(state.get("retrieval_attempts", 0))
    max_attempts = int(state.get("max_retrieval_attempts", 1))
    rewrite_enabled = bool(state.get("enable_query_rewrite", True))
    context = state.get("context", {})
    has_context = bool(str(context.get("context_prompt", "")).strip())

    if grade in {"weak", "none"} and rewrite_enabled and attempts < max_attempts:
        return "rewrite_query"

    if grade == "none" and not has_context:
        return "no_context_fallback"

    return "answer_generator"


def route_after_answer(state: AgenticRAGState) -> str:
    return "save_thread_state"
