# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from collections.abc import AsyncIterator
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMGenerationSettings:
    # generative settings
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.0

    # max response token
    max_tokens: int = 1024
    # max context: prompt + query + response
    num_ctx: int = 4096
    # stop tokens
    stop: str | list[str] | None = None

    # hardware settings
    keep_alive: str | int = "10m"
    seed: int | None = None


@dataclass(frozen=True)
class LLMUsageMetadata:
    prompt_tokens: int  # did retrieved context fit in num_ctx?
    completion_tokens: int  # output volume
    total_tokens: int  # prompt_tokens + completion_tokens
    prompt_eval_duration_ms: float  # context-processing bottleneck
    eval_duration_ms: float  # generation-speed bottleneck
    load_duration_ms: float  # keep_alive misconfiguration signal
    latency_ms: float  # top-line total


@dataclass(frozen=True)
class LLMGenerationResult:
    text: str
    provider: str
    model_name: str
    usage: LLMUsageMetadata
    raw_response: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    provider_name: str
    model_name: str

    @abstractmethod
    async def close(self) -> None:
        """
        close provider resources
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        check provider backend availability
        """

    @abstractmethod
    async def generate(
        self, prompt: str, settings: LLMGenerationSettings
    ) -> LLMGenerationResult:
        """
        one time generation, returned when prompt is fully answered
        """

    @abstractmethod
    async def stream(
        self, prompt: str, settings: LLMGenerationSettings
    ) -> AsyncIterator[str]:
        """
        stream response message in real-time without having to wait for full answer
        """
