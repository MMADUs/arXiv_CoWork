# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.service.arxiv.smart_search.state import SmartSearchState


def route_after_guardrail(state: SmartSearchState) -> str:
    if state.get("blocked"):
        return "format_results"

    return "extract_knowledge"
