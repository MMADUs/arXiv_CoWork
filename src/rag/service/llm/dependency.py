# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import Request

from rag.service.llm.interface import LLMProvider


def get_llm_provider(request: Request) -> LLMProvider:
    """
    FastAPI dependency for LLM (large language model) provider
    """
    llm_provider: LLMProvider | None = getattr(request.app.state, "llm_provider", None)

    if llm_provider is None:
        raise RuntimeError("llm_provider is not initialized on app.state")

    return llm_provider
