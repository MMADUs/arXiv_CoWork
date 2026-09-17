# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class LLMGenerationSettings:
    """
    LLM generation settings control the quality and constraints of the response.
    """

    # generative settings
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.0
    reasoning: bool | None = None

    # max response token
    max_tokens: int = 2048
    # max context: prompt + query + response
    num_ctx: int = 8192
    # stop tokens
    stop: str | list[str] | None = None
    # structured response format, for providers that support it
    response_format: Literal["json"] | None = None

    # hardware settings
    keep_alive: str | int = "10m"
    seed: int | None = None


@dataclass(frozen=True)
class LLMUsageMetadata:
    """
    Response schema for LLM usage metadata after text generation
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int  # prompt_tokens + completion_tokens
    prefill_duration_ms: float
    decode_duration_ms: float
    model_load_duration_ms: float
    latency_ms: float  # from input to finish generating


@dataclass(frozen=True)
class LLMGenerationResult:
    """
    Response schema for LLM text generation
    """

    response_text: str
    provider: str
    model_name: str
    usage: LLMUsageMetadata
    raw_response: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """
    Any LLM providers must inherit the `LLMProvider` class,
    this keeps any module that are dependent consistent when switching provider
    """

    provider_name: str
    model_name: str

    @abstractmethod
    async def close(self) -> None:
        """
        close provider resources
        """

    @abstractmethod
    async def health_check(self) -> tuple[bool, str]:
        """
        check provider backend availability

        Returns:
            boolean flag if connection is ok and any successful message
        """

    @abstractmethod
    async def generate(
        self, prompt: str, settings: LLMGenerationSettings
    ) -> LLMGenerationResult:
        """
        one time generation, returned when prompt is fully answered
        """

    @abstractmethod
    def stream(
        self, prompt: str, settings: LLMGenerationSettings
    ) -> AsyncIterator[str]:
        """
        stream response message in real-time without having to wait for full answer
        """
