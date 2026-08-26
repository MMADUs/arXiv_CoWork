# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from rag.config import OllamaLLMSettings
from rag.service.llm.llm_exceptions import (
    LLMConnectionError,
    LLMProviderError,
    LLMResponseError,
    LLMTimeoutError,
    LLMValidationError,
)
from rag.service.llm.llm_interface import (
    LLMGenerationResult,
    LLMGenerationSettings,
    LLMProvider,
    LLMUsageMetadata,
)

logger = logging.getLogger(__name__)


class OllamaLLMProvider(LLMProvider):
    """
    Ollama LLM provider.

    Uses Ollama's `/api/generate` endpoint to generate text from a prompt.
    The provider supports both full-response generation and token streaming
    through the same endpoint by toggling Ollama's `stream` request field.

    Generation requests include the configured model name, prompt, sampling
    options, optional structured JSON output, and optional keep-alive behavior.

    Provider health is checked through Ollama's `/api/tags` endpoint.
    """

    provider_name = "ollama"

    def __init__(self, settings: OllamaLLMSettings) -> None:
        # satisfy interface
        self.model_name = settings.model_name

        self.base_url = settings.base_url.rstrip("/")
        self.max_retries = settings.max_retries
        self.retry_backoff_seconds = settings.retry_backoff_seconds
        self.last_stream_usage: LLMUsageMetadata | None = None

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health_check(self) -> tuple[bool, str]:
        try:
            response = await self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return True, "Ollama LLM connected"

        except httpx.HTTPError as error:
            return False, str(error)

    async def generate(
        self, prompt: str, settings: LLMGenerationSettings
    ) -> LLMGenerationResult:
        """
        Generate response from the given prompt, the function awaits async process
        until the model generates the end-of-text token.

        Args:
            prompts:
                the full prompt including user query and available context
            settings:
                generation settings, affect generation result

        Raises:
            LLMValidationError:
                If the given prompt is empty
            LLMProviderError:
                If the Ollama request fails after retries
            LLMConnectionError:
                If Ollama cannot be reached after retries
            LLMTimeoutError:
                If Ollama times out after retries
            LLMResponseError:
                If the response payload is invalid, malformed JSON, or missing keys
        """
        if not prompt.strip():
            raise LLMValidationError("Cannot generate from an empty prompt")

        payload = self._make_payload(prompt=prompt, settings=settings, stream=False)
        data = await self._post_with_retries("/api/generate", payload)

        response_text = data.get("response")

        if not isinstance(response_text, str):
            raise LLMResponseError("Ollama generation response did not include text.")

        return LLMGenerationResult(
            response_text=response_text,
            provider=self.provider_name,
            model_name=self.model_name,
            usage=self._make_usage_metadata(data),
            raw_response=data,
        )

    async def stream(
        self, prompt: str, settings: LLMGenerationSettings
    ) -> AsyncIterator[str]:
        """
        Stream response chunks from the given prompt as the model generates tokens.
        Failed streams are retried only before any token has been yielded.

        Args:
            prompt:
                the full prompt including user query and available context
            settings:
                generation settings, affect generation result

        Raises:
            LLMValidationError:
                If the given prompt is empty
            LLMProviderError:
                If the Ollama stream fails after retries
            LLMConnectionError:
                If Ollama cannot be reached after retries
            LLMTimeoutError:
                If Ollama times out after retries
            LLMResponseError:
                If the stream payload is invalid, either invalid JSON or invalid status
        """
        if not prompt.strip():
            raise LLMValidationError("Cannot generate from an empty prompt")

        payload = self._make_payload(prompt=prompt, settings=settings, stream=True)

        self.last_stream_usage = None
        yielded_any = False
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with self._client.stream(
                    "POST", f"{self.base_url}/api/generate", json=payload
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)

                        except json.JSONDecodeError as error:
                            raise LLMResponseError(
                                f"Ollama stream returned malformed JSON: {line}"
                            ) from error

                        if data.get("done"):
                            self.last_stream_usage = self._make_usage_metadata(data)
                            continue

                        text = data.get("response")

                        if isinstance(text, str) and text:
                            yielded_any = True
                            yield text

                return

            except httpx.ConnectError as error:
                last_exc = LLMConnectionError(
                    f"Could not connect to Ollama at {self.base_url}: {error}"
                )

            except httpx.TimeoutException as error:
                last_exc = LLMTimeoutError(f"Ollama stream timed out: {error}")

            except httpx.HTTPStatusError as error:
                if 500 <= error.response.status_code < 600:
                    last_exc = LLMProviderError(
                        "Ollama returned server error: "
                        f"{error.response.status_code}: {error.response.text}"
                    )
                else:
                    raise LLMResponseError(
                        "Ollama returned "
                        f"{error.response.status_code}: {error.response.text}"
                    ) from error

            except LLMResponseError:
                raise

            except LLMProviderError as error:
                last_exc = error

            if yielded_any or attempt >= self.max_retries:
                assert last_exc is not None
                raise last_exc

            backoff = self.retry_backoff_seconds * (2**attempt)

            logger.warning(
                "Ollama stream failed before yielding tokens "
                "(attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                self.max_retries + 1,
                backoff,
                last_exc,
            )

            await asyncio.sleep(backoff)

        assert last_exc is not None
        raise last_exc

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

                data = response.json()
                if not isinstance(data, dict):
                    raise LLMResponseError(
                        "Ollama generation response must be a JSON object"
                    )

                return data

            except httpx.ConnectError as error:
                last_exc = LLMConnectionError(
                    f"Could not connect to Ollama at {self.base_url}: {error}"
                )

            except httpx.TimeoutException as error:
                last_exc = LLMTimeoutError(f"Ollama request timed out: {error}")

            except httpx.HTTPStatusError as error:
                if 500 <= error.response.status_code < 600:
                    last_exc = LLMProviderError(
                        "Ollama returned server error: "
                        f"{error.response.status_code}: {error.response.text}"
                    )
                else:
                    raise LLMResponseError(
                        "Ollama returned "
                        f"{error.response.status_code}: {error.response.text}"
                    ) from error

            except json.JSONDecodeError as error:
                raise LLMResponseError(
                    "Ollama generation response was not valid JSON"
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

        if settings.reasoning is not None:
            payload["think"] = settings.reasoning

        if settings.response_format == "json":
            payload["format"] = "json"

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
