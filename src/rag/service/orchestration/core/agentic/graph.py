# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

from langgraph.graph import END, START, StateGraph

from rag.service.orchestration.core.agentic.edges import (
    route_after_critic,
    route_after_evidence,
    route_after_followup,
    route_after_guardrail,
    route_after_scope,
)
from rag.service.orchestration.core.agentic.nodes import AgenticRAGNodes
from rag.service.orchestration.core.agentic.state import AgenticRAGState


def build_agentic_rag_graph(
    nodes: AgenticRAGNodes,
    checkpointer: Any | None = None,
):
    graph = StateGraph(AgenticRAGState)

    graph.add_node("input_guardrail", nodes.input_guardrail)
    graph.add_node("scope_router", nodes.scope_router)
    graph.add_node("followup_router", nodes.followup_router)
    graph.add_node("retrieval_planner", nodes.retrieval_planner)
    graph.add_node("retrieve", nodes.retrieve)
    graph.add_node("rerank", nodes.rerank)
    graph.add_node("build_context", nodes.build_context)
    graph.add_node("evidence_grader", nodes.evidence_grader)
    graph.add_node("rewrite_query", nodes.rewrite_query)
    graph.add_node("no_context_fallback", nodes.no_context_fallback)
    graph.add_node("answer_generator", nodes.answer_generator)
    graph.add_node("citation_verifier", nodes.citation_verifier)
    graph.add_node("answer_critic", nodes.answer_critic)
    graph.add_node("answer_repair", nodes.answer_repair)
    graph.add_node("targeted_retrieval", nodes.targeted_retrieval)
    graph.add_node("save_thread_state", nodes.save_thread_state)

    graph.add_edge(START, "input_guardrail")
    graph.add_conditional_edges("input_guardrail", route_after_guardrail)
    graph.add_conditional_edges("scope_router", route_after_scope)
    graph.add_conditional_edges("followup_router", route_after_followup)
    graph.add_edge("retrieval_planner", "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "build_context")
    graph.add_edge("build_context", "evidence_grader")
    graph.add_conditional_edges("evidence_grader", route_after_evidence)
    graph.add_edge("rewrite_query", "retrieval_planner")
    graph.add_edge("answer_generator", "citation_verifier")
    graph.add_edge("citation_verifier", "answer_critic")
    graph.add_conditional_edges("answer_critic", route_after_critic)
    graph.add_edge("answer_repair", "citation_verifier")
    graph.add_edge("targeted_retrieval", "retrieval_planner")
    graph.add_edge("no_context_fallback", "save_thread_state")
    graph.add_edge("save_thread_state", END)

    return graph.compile(checkpointer=checkpointer)
