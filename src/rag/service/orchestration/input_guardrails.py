# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from rag.service.llm import LLMGenerationSettings, LLMProvider, LLMServiceError
from rag.service.orchestration.prompts import GUARDRAIL_PROMPT_V1
from rag.service.orchestration.utils import parse_json_object


class InputGuardrailError(Exception):
    """Internal exception for input guardrail evaluation failures"""


class GuardrailDecision(StrEnum):
    """
    Input guardrail decision string enum class

    Available enum members:
    - ALLOW
    - BLOCK
    """

    ALLOW = "allow"
    BLOCK = "block"


class GuardrailRiskLevel(StrEnum):
    """
    Input guardrail risk level string enum class

    Available enum members:
    - LOW
    - MEDIUM
    - HIGH
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class InputGuardrailResult:
    """
    Response schema from input guardrails prompt validation
    """

    decision: GuardrailDecision
    risk_level: GuardrailRiskLevel
    categories: list[str]
    reason: str | None
    safe_query: str | None
    response: str | None
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision == GuardrailDecision.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "categories": self.categories,
            "reason": self.reason,
            "safe_query": self.safe_query,
            "response": self.response,
            "raw_response": self.raw_response,
        }


class InputGuardrails:
    """
    InputGuardrails validates a user query before orchestration continues,
    through `evaluate_user_query()` method.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        settings: LLMGenerationSettings | None = None,
        max_query_length: int = 4_000,
    ) -> None:
        if max_query_length < 1:
            raise InputGuardrailError("max_query_chars must be greater than 0")

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
        self.max_query_length = max_query_length

    async def evaluate_user_query(self, query: str) -> InputGuardrailResult:
        """
        Validate and sanitize a user query before retrieval and generation.

        LLM service errors and guardrail parsing errors are handled internally
        and returned as failed-closed block results.

        Args:
            query:
                user query to validate (raw user query only without document/context)
        """
        normalized_query = self._normalize_query(query)
        local_block = self._local_block_reason(normalized_query)

        if local_block is not None:
            return InputGuardrailResult(
                decision=GuardrailDecision.BLOCK,
                risk_level=GuardrailRiskLevel.HIGH,
                categories=["invalid_input"],
                reason=local_block,
                safe_query=None,
                response=(
                    "Sorry, I need a valid question before I can search "
                    "the indexed papers."
                ),
                raw_response={},
            )

        guardrail_prompt = self._build_prompt(normalized_query)

        try:
            generation = await self.llm_provider.generate(
                prompt=guardrail_prompt,
                settings=self.settings,
            )
            raw_payload = self._parse_response(generation.response_text)
            return self._make_result(raw_payload)

        except LLMServiceError as error:
            return InputGuardrailResult(
                decision=GuardrailDecision.BLOCK,
                risk_level=GuardrailRiskLevel.HIGH,
                categories=["guardrail_llm_failure"],
                reason=f"Input guardrail LLM validation failed closed: {error}",
                safe_query=None,
                response="Sorry, I can't safely validate that request right now.",
                raw_response={},
            )

        except InputGuardrailError as error:
            return InputGuardrailResult(
                decision=GuardrailDecision.BLOCK,
                risk_level=GuardrailRiskLevel.HIGH,
                categories=["guardrail_failure"],
                reason=f"Input guardrail validation failed closed: {error}",
                safe_query=None,
                response="Sorry, I can't safely validate that request right now.",
                raw_response={},
            )

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.split())

    def _local_block_reason(self, normalized_query: str) -> str | None:
        if not normalized_query:
            return "Question is empty."

        if len(normalized_query) > self.max_query_length:
            return "Question is too long."

        if not any(char.isalnum() for char in normalized_query):
            return "Question must contain alphanumeric text."

        return None

    def _build_prompt(self, query: str) -> str:
        return GUARDRAIL_PROMPT_V1.format(query=query)

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        try:
            return parse_json_object(response_text)

        except ValueError as error:
            raise InputGuardrailError("Guardrail response is not valid JSON") from error

    def _make_result(self, data: dict[str, Any]) -> InputGuardrailResult:
        decision_value = data.get("decision")
        risk_level_value = data.get("risk_level")
        categories = data.get("categories", [])
        reason = data.get("reason")
        safe_query = data.get("safe_query")
        response = data.get("response")

        try:
            decision = GuardrailDecision(str(decision_value))

        except ValueError as error:
            raise InputGuardrailError(
                "Guardrail decision must be allow or block"
            ) from error

        try:
            risk_level = GuardrailRiskLevel(str(risk_level_value))

        except ValueError as error:
            raise InputGuardrailError(
                "Guardrail risk_level must be low, medium, or high"
            ) from error

        if not isinstance(categories, list):
            raise InputGuardrailError("Guardrail categories must be a list")

        category_values = [str(category) for category in categories]

        if reason is not None:
            reason = str(reason)

        if safe_query is not None:
            safe_query = self._normalize_query(str(safe_query))

        if response is not None:
            response = self._normalize_query(str(response))

        if decision == GuardrailDecision.ALLOW and not safe_query:
            raise InputGuardrailError(
                "Allowed guardrail result must include safe_query"
            )

        if decision == GuardrailDecision.BLOCK and safe_query is not None:
            raise InputGuardrailError(
                "Blocked guardrail result must not include safe_query"
            )

        if decision == GuardrailDecision.ALLOW and response is not None:
            raise InputGuardrailError(
                "Allowed guardrail result must not include response"
            )

        if decision == GuardrailDecision.BLOCK and not response:
            raise InputGuardrailError("Blocked guardrail result must include response")

        return InputGuardrailResult(
            decision=decision,
            risk_level=risk_level,
            categories=category_values,
            reason=reason,
            safe_query=safe_query,
            response=response,
            raw_response=data,
        )
