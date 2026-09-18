# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from rag.service.arxiv.smart_search.prompts import (
    SMART_SEARCH_ADVANCED_QUERY_PLANNER_PROMPT_V1,
    SMART_SEARCH_KNOWLEDGE_EXTRACTION_PROMPT_V1,
)
from rag.service.arxiv.smart_search.schemas import ArxivQueryPlan, SmartSearchKnowledge
from rag.service.arxiv.smart_search.state import (
    SmartSearchState,
    knowledge_to_state,
    plan_to_state,
)
from rag.service.llm import LLMGenerationSettings, LLMProvider
from rag.service.orchestration.input_guardrails import InputGuardrails
from rag.service.orchestration.utils import parse_json_object

logger = logging.getLogger(__name__)


class SmartSearchNodes:
    """
    Nodes for agentic arXiv smart search query planning.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        input_guardrails: InputGuardrails | None = None,
        status_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.input_guardrails = input_guardrails or InputGuardrails(llm_provider)
        self.status_callback = status_callback
        self.knowledge_settings = LLMGenerationSettings(
            temperature=0.0,
            top_p=1.0,
            top_k=1,
            repeat_penalty=1.0,
            max_tokens=256,
            num_ctx=4096,
            response_format="json",
        )
        self.planner_settings = LLMGenerationSettings(
            temperature=0.1,
            top_p=0.9,
            top_k=20,
            max_tokens=700,
            num_ctx=8192,
            response_format="json",
        )

    async def input_guardrail(self, state: SmartSearchState) -> dict[str, Any]:
        await self._emit_status("Reading user request...")

        user_query = " ".join(state.get("user_query", "").split())
        guardrail = await self.input_guardrails.evaluate_user_query(user_query)

        fresh_state: dict[str, Any] = {
            "user_query": user_query,
            "safe_query": guardrail.safe_query or "",
            "blocked": not guardrail.allowed,
            "guardrail": guardrail.to_dict(),
            "knowledge": {},
            "raw_plan": {},
            "plan": {},
            "query_params": {},
            "summary": "",
            "response": "",
            "errors": [],
            "metadata": {},
        }

        if not guardrail.allowed:
            return {
                **fresh_state,
                "response": guardrail.response
                or "Sorry, I can't safely use that request for smart search.",
            }

        return {
            **fresh_state,
            "safe_query": guardrail.safe_query or user_query,
        }

    async def extract_knowledge(self, state: SmartSearchState) -> dict[str, Any]:
        await self._emit_status("Searching keyword...")

        try:
            prompt = SMART_SEARCH_KNOWLEDGE_EXTRACTION_PROMPT_V1.format(
                query=state["safe_query"],
            )

            payload = await self._generate_llm_json_response(
                prompt,
                generation_settings=self.knowledge_settings,
            )

            knowledge = SmartSearchKnowledge.model_validate(payload)

        except Exception as error:
            logger.warning(
                "Smart search knowledge extraction failed; using safe query fallback",
                exc_info=True,
            )
            fallback = SmartSearchKnowledge(
                title=None,
                keywords=[state["safe_query"]],
                authors=[],
            )
            return {
                "knowledge": knowledge_to_state(fallback),
                "errors": [
                    *state.get("errors", []),
                    f"knowledge extraction failed; using safe query fallback: {error}",
                ],
            }

        return {
            "knowledge": knowledge_to_state(knowledge),
        }

    async def plan_advanced_query(self, state: SmartSearchState) -> dict[str, Any]:
        await self._emit_status("Building search plan...")

        try:
            prompt = SMART_SEARCH_ADVANCED_QUERY_PLANNER_PROMPT_V1.format(
                query=state["safe_query"],
                knowledge=json.dumps(state.get("knowledge", {}), ensure_ascii=True),
            )

            payload = await self._generate_llm_json_response(
                prompt,
                generation_settings=self.planner_settings,
            )

        except Exception as error:
            logger.warning(
                "Smart search advanced query planning failed",
                exc_info=True,
            )
            return {
                "raw_plan": {},
                "errors": [
                    *state.get("errors", []),
                    f"advanced query planning failed: {error}",
                ],
            }

        return {
            "raw_plan": payload,
        }

    async def format_results(self, state: SmartSearchState) -> dict[str, Any]:
        if state.get("blocked"):
            return {
                "summary": "Smart search request was blocked by input guardrails.",
            }

        errors = state.get("errors", [])

        try:
            plan = ArxivQueryPlan.model_validate(state.get("raw_plan", {}))
            query_params = plan.to_query_params()

        except Exception as error:
            logger.warning(
                "Smart search query plan validation failed",
                exc_info=True,
            )
            return {
                "summary": "Smart search could not produce executable query params.",
                "errors": [*errors, f"query plan validation failed: {error}"],
            }

        summary = "Smart search produced executable arXiv query params."

        if errors:
            summary += " Knowledge extraction used a fallback."

        return {
            "plan": plan_to_state(plan),
            "query_params": query_params.model_dump(mode="json"),
            "summary": summary,
        }

    async def _generate_llm_json_response(
        self,
        prompt: str,
        generation_settings: LLMGenerationSettings,
    ) -> dict[str, Any]:
        generation = await self.llm_provider.generate(
            prompt=prompt,
            settings=generation_settings,
        )
        return parse_json_object(generation.response_text)

    async def _emit_status(self, text: str) -> None:
        if self.status_callback is not None:
            await self.status_callback(text)
