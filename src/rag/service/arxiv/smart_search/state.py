# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any, Literal, TypedDict

from rag.service.arxiv.smart_search.schemas import ArxivQueryPlan, SmartSearchKnowledge


SmartSearchRoute = Literal[
    "input_guardrail",
    "extract_knowledge",
    "plan_advanced_query",
    "format_results",
]


class SmartSearchState(TypedDict, total=False):
    user_query: str
    safe_query: str
    blocked: bool
    guardrail: dict[str, Any]
    knowledge: dict[str, Any]
    raw_plan: dict[str, Any]
    plan: dict[str, Any]
    query_params: dict[str, Any]
    summary: str
    response: str
    errors: list[str]
    metadata: dict[str, Any]


def knowledge_to_state(knowledge: SmartSearchKnowledge) -> dict[str, Any]:
    return knowledge.model_dump(mode="json")


def plan_to_state(plan: ArxivQueryPlan) -> dict[str, Any]:
    return plan.model_dump(mode="json")
