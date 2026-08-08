# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from rag.service.llm import LLMGenerationSettings, LLMProvider
from rag.service.orchestration.direct.prompts import INPUT_GUARDRAIL_PROMPT

GuardrailDecision = Literal["allow", "block"]
GuardrailRiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class InputGuardrailResult:
    decision: GuardrailDecision
    risk_level: GuardrailRiskLevel
    categories: list[str]
    reason: str | None
    safe_query: str | None
    response: str | None
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "risk_level": self.risk_level,
            "categories": self.categories,
            "reason": self.reason,
            "safe_query": self.safe_query,
            "response": self.response,
            "raw_response": self.raw_response,
        }


class InputGuardrails:
    def __init__(
        self,
        llm_provider: LLMProvider,
        settings: LLMGenerationSettings | None = None,
        max_query_chars: int = 4_000,
    ) -> None:
        if max_query_chars < 1:
            raise ValueError("max_query_chars must be greater than 0")

        self.llm_provider = llm_provider
        self.settings = settings or LLMGenerationSettings(
            temperature=0.0,
            top_p=1.0,
            top_k=1,
            repeat_penalty=1.0,
            max_tokens=256,
            num_ctx=2048,
            response_format="json",
        )
        self.max_query_chars = max_query_chars

    async def evaluate(self, query: str) -> InputGuardrailResult:
        normalized_query = self._normalize_query(query)
        local_block = self._local_block_reason(normalized_query)

        if local_block is not None:
            return InputGuardrailResult(
                decision="block",
                risk_level="high",
                categories=["invalid_input"],
                reason=local_block,
                safe_query=None,
                response="Sorry, I need a valid question before I can search the indexed papers.",
                raw_response={},
            )

        prompt = self._build_prompt(normalized_query)

        try:
            generation = await self.llm_provider.generate(
                prompt=prompt,
                settings=self.settings,
            )
            raw_payload = self._parse_json_object(generation.text)
            return self._make_result(raw_payload)

        except Exception as error:
            fallback = self._fallback_result(normalized_query, error)

            if fallback is not None:
                return fallback

            return InputGuardrailResult(
                decision="block",
                risk_level="high",
                categories=["guardrail_failure"],
                reason=f"Input guardrail failed closed: {error}",
                safe_query=None,
                response="Sorry, I can't safely process that request right now.",
                raw_response={},
            )

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.split())

    def _local_block_reason(self, normalized_query: str) -> str | None:
        if not normalized_query:
            return "Question is empty."

        if len(normalized_query) > self.max_query_chars:
            return "Question is too long."

        if not any(char.isalnum() for char in normalized_query):
            return "Question must contain alphanumeric text."

        return None

    def _fallback_result(
        self,
        normalized_query: str,
        error: Exception,
    ) -> InputGuardrailResult | None:
        local_block = self._local_policy_block_reason(normalized_query)

        if local_block is not None:
            return InputGuardrailResult(
                decision="block",
                risk_level="high",
                categories=["local_policy_block", "guardrail_parse_failure"],
                reason=f"{local_block} Guardrail parse failed: {error}",
                safe_query=None,
                response="Sorry, I can help with indexed paper questions, but not with that request.",
                raw_response={},
            )

        return InputGuardrailResult(
            decision="allow",
            risk_level="medium",
            categories=["guardrail_parse_fallback"],
            reason=f"Guardrail parse failed; allowed by conservative local fallback: {error}",
            safe_query=normalized_query,
            response=None,
            raw_response={},
        )

    def _local_policy_block_reason(self, normalized_query: str) -> str | None:
        query = normalized_query.lower()
        blocked_phrases = [
            "system prompt",
            "developer prompt",
            "hidden prompt",
            "guardrail prompt",
            "ignore previous",
            "ignore all previous",
            "bypass",
            "override instructions",
            "api key",
            "credentials",
            "environment variable",
            "env var",
            "database password",
            "run shell",
            "shell command",
            "delete index",
            "drop table",
        ]

        for phrase in blocked_phrases:
            if phrase in query:
                return f"Request matched blocked local policy phrase: {phrase}."

        return None

    def _build_prompt(self, query: str) -> str:
        return INPUT_GUARDRAIL_PROMPT.format(query=query)

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        stripped = text.strip()

        if stripped.startswith("```"):
            stripped = stripped.strip("`").strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()

        start = stripped.find("{")
        end = stripped.rfind("}")

        if start == -1 or end == -1 or end < start:
            raise ValueError("Guardrail response did not contain a JSON object")

        data = json.loads(stripped[start : end + 1])

        if not isinstance(data, dict):
            raise ValueError("Guardrail response JSON must be an object")

        return data

    def _make_result(self, data: dict[str, Any]) -> InputGuardrailResult:
        decision = data.get("decision")
        risk_level = data.get("risk_level")
        categories = data.get("categories", [])
        reason = data.get("reason")
        safe_query = data.get("safe_query")
        response = data.get("response")

        if decision not in {"allow", "block"}:
            raise ValueError("Guardrail decision must be allow or block")

        if risk_level not in {"low", "medium", "high"}:
            raise ValueError("Guardrail risk_level must be low, medium, or high")

        if not isinstance(categories, list):
            raise ValueError("Guardrail categories must be a list")

        category_values = [str(category) for category in categories]

        if reason is not None:
            reason = str(reason)

        if safe_query is not None:
            safe_query = self._normalize_query(str(safe_query))

        if response is not None:
            response = self._normalize_query(str(response))

        if decision == "allow" and not safe_query:
            raise ValueError("Allowed guardrail result must include safe_query")

        if decision == "block" and safe_query is not None:
            raise ValueError("Blocked guardrail result must not include safe_query")

        if decision == "allow" and response is not None:
            raise ValueError("Allowed guardrail result must not include response")

        if decision == "block" and not response:
            raise ValueError("Blocked guardrail result must include response")

        return InputGuardrailResult(
            decision=decision,
            risk_level=risk_level,
            categories=category_values,
            reason=reason,
            safe_query=safe_query,
            response=response,
            raw_response=data,
        )
