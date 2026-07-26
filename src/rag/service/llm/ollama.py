# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from rag.config import OllamaLLMSettings
from rag.service.llm.interface import (
    LLMGenerationResult,
    LLMGenerationSettings,
    LLMProvider,
    LLMUsageMetadata,
)
from rag.service.llm.exception import (
    LLMConnectionError,
    LLMResponseError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class OllamaLLMProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(self, settings: OllamaLLMSettings) -> None:
        self.base_url = settings.base_url.rstrip("/")
        self.model_name = settings.model_name
        self.max_retries = settings.max_retries
        self.retry_backoff_seconds = settings.retry_backoff_seconds
        self.last_stream_usage: LLMUsageMetadata | None = None

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return True

        except httpx.HTTPError:
            return False

    async def generate(
        self, prompt: str, settings: LLMGenerationSettings
    ) -> LLMGenerationResult:
        if not prompt.strip():
            raise ValueError("Cannot generate from an empty prompt.")

        payload = self._make_payload(prompt=prompt, settings=settings, stream=False)
        data = await self._post_with_retries("/api/generate", payload)

        text = data.get("response")

        if not isinstance(text, str):
            raise LLMResponseError("Ollama generation response did not include text.")

        return LLMGenerationResult(
            text=text,
            provider=self.provider_name,
            model_name=self.model_name,
            usage=self._make_usage_metadata(data),
            raw_response=data,
        )

    async def stream(
        self, prompt: str, settings: LLMGenerationSettings
    ) -> AsyncIterator[str]:
        if not prompt.strip():
            raise ValueError("Cannot generate from an empty prompt.")

        payload = self._make_payload(prompt=prompt, settings=settings, stream=True)

        self.last_stream_usage = None

        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/api/generate", json=payload
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    data = json.loads(line)

                    if data.get("done"):
                        self.last_stream_usage = self._make_usage_metadata(data)
                        continue

                    text = data.get("response")
                    if isinstance(text, str) and text:
                        yield text

        except httpx.TimeoutException as error:
            raise LLMTimeoutError(f"Ollama stream timed out: {error}") from error

        except httpx.ConnectError as error:
            raise LLMConnectionError(
                f"Could not connect to Ollama at {self.base_url}: {error}"
            ) from error

        except httpx.HTTPStatusError as error:
            raise LLMResponseError(
                f"Ollama returned {error.response.status_code}: {error.response.text}"
            ) from error

    async def _post_with_retries(
        self, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self.base_url}{path}", json=payload
                )
                response.raise_for_status()

                return response.json()

            except httpx.ConnectError as error:
                last_exc = LLMConnectionError(
                    f"Could not connect to Ollama at {self.base_url}: {error}"
                )

            except httpx.TimeoutException as error:
                last_exc = LLMTimeoutError(f"Ollama request timed out: {error}")

            except httpx.HTTPStatusError as error:
                if (
                    500 <= error.response.status_code < 600
                    and attempt < self.max_retries
                ):
                    last_exc = LLMResponseError(
                        f"Ollama returned {error.response.status_code}: {error.response.text}"
                    )
                else:
                    raise LLMResponseError(
                        f"Ollama returned {error.response.status_code}: {error.response.text}"
                    ) from error

            if attempt < self.max_retries:
                backoff = self.retry_backoff_seconds * (2**attempt)

                logger.warning(
                    "Ollama request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    backoff,
                    last_exc,
                )

                await asyncio.sleep(backoff)

        assert last_exc is not None
        raise last_exc

    def _make_payload(
        self, prompt: str, settings: LLMGenerationSettings, stream: bool
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "top_k": settings.top_k,
            "repeat_penalty": settings.repeat_penalty,
            "num_predict": settings.max_tokens,
            "num_ctx": settings.num_ctx,
        }

        if settings.stop:
            options["stop"] = settings.stop

        if settings.seed is not None:
            options["seed"] = settings.seed

        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": stream,
            "options": options,
        }

        if settings.keep_alive is not None:
            payload["keep_alive"] = settings.keep_alive

        return payload

    def _make_usage_metadata(self, data: dict[str, Any]) -> LLMUsageMetadata:
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        return LLMUsageMetadata(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            prompt_eval_duration_ms=self._ns_to_ms(data.get("prompt_eval_duration")),
            eval_duration_ms=self._ns_to_ms(data.get("eval_duration")),
            load_duration_ms=self._ns_to_ms(data.get("load_duration")),
            latency_ms=self._ns_to_ms(data.get("total_duration")),
        )

    def _ns_to_ms(self, value: Any) -> float:
        if not isinstance(value, int | float):
            return 0.0

        return round(value / 1_000_000, 2)
