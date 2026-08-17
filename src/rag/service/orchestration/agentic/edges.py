# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.service.orchestration.agentic.state import AgenticRAGState


def route_after_guardrail(state: AgenticRAGState) -> str:
    if state.get("blocked"):
        return "save_thread_state"

    return "scope_router"


def route_after_scope(state: AgenticRAGState) -> str:
    decision = state.get("scope", {}).get("decision")

    if decision in {"direct_response", "out_of_scope"}:
        return "save_thread_state"

    return "followup_router"


def route_after_followup(state: AgenticRAGState) -> str:
    if state.get("followup", {}).get("route") == "use_active_context":
        return "build_context"

    return "retrieval_planner"


def route_after_evidence(state: AgenticRAGState) -> str:
    grade = state.get("evidence_grade", {}).get("grade")
    attempts = int(state.get("retrieval_attempts", 0))
    max_attempts = int(state.get("max_retrieval_attempts", 1))
    rewrite_enabled = bool(state.get("enable_query_rewrite", True))

    if grade in {"weak", "none"} and rewrite_enabled and attempts < max_attempts:
        return "rewrite_query"

    if grade == "none":
        return "no_context_fallback"

    return "answer_generator"


def route_after_critic(state: AgenticRAGState) -> str:
    verdict = state.get("answer_critique", {}).get("verdict")
    retrieval_attempts = int(state.get("retrieval_attempts", 0))
    max_retrieval_attempts = int(state.get("max_retrieval_attempts", 1))
    repair_attempts = int(state.get("answer_repair_attempts", 0))
    max_repair_attempts = int(state.get("max_answer_repair_attempts", 0))
    repair_enabled = bool(state.get("enable_answer_repair", True))
    post_answer_retrieval_enabled = bool(
        state.get("enable_post_answer_retrieval", True)
    )

    if verdict == "pass":
        return "save_thread_state"

    if (
        verdict == "fail"
        and post_answer_retrieval_enabled
        and retrieval_attempts < max_retrieval_attempts
    ):
        return "targeted_retrieval"

    if (
        verdict in {"repair", "fail"}
        and repair_enabled
        and repair_attempts < max_repair_attempts
    ):
        return "answer_repair"

    if verdict == "fail":
        return "no_context_fallback"

    return "save_thread_state"
