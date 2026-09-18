# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

from langgraph.graph import END, START, StateGraph

from rag.service.arxiv.smart_search.edges import route_after_guardrail
from rag.service.arxiv.smart_search.nodes import SmartSearchNodes
from rag.service.arxiv.smart_search.state import SmartSearchState


def build_smart_search_graph(
    nodes: SmartSearchNodes,
    checkpointer: Any | None = None,
):
    graph = StateGraph(SmartSearchState)

    graph.add_node("input_guardrail", nodes.input_guardrail)
    graph.add_node("extract_knowledge", nodes.extract_knowledge)
    graph.add_node("plan_advanced_query", nodes.plan_advanced_query)
    graph.add_node("format_results", nodes.format_results)

    graph.add_edge(START, "input_guardrail")
    graph.add_conditional_edges("input_guardrail", route_after_guardrail)
    graph.add_edge("extract_knowledge", "plan_advanced_query")
    graph.add_edge("plan_advanced_query", "format_results")
    graph.add_edge("format_results", END)

    return graph.compile(checkpointer=checkpointer)
