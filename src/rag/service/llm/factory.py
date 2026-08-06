# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import Settings, get_settings
from rag.service.llm.interface import LLMProvider
from rag.service.llm.ollama import OllamaLLMProvider


def create_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()

    return OllamaLLMProvider(settings=settings.llm_settings)
