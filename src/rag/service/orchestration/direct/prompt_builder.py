# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from typing import Any

from rag.service.orchestration.direct.context_builder import BuiltContext
from rag.service.orchestration.direct.prompts import (
    ANSWER_GENERATION_PROMPT,
    NO_CONTEXT_ANSWER_PROMPT,
)


@dataclass(frozen=True, slots=True)
class BuiltPrompt:
    prompt: str
    question: str
    source_count: int
    context_char_count: int
    has_context: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "question": self.question,
            "source_count": self.source_count,
            "context_char_count": self.context_char_count,
            "has_context": self.has_context,
        }


class PromptBuilder:
    def __init__(
        self,
        assistant_role: str = "You are an arXiv paper research assistant.",
        no_context_message: str = (
            "The indexed sources are insufficient to answer this question."
        ),
    ) -> None:
        self.assistant_role = assistant_role
        self.no_context_message = no_context_message

    def build(self, question: str, context: BuiltContext) -> BuiltPrompt:
        normalized_question = self._normalize_question(question)
        has_context = bool(context.prompt_context.strip())

        prompt = (
            self._build_context_prompt(normalized_question, context)
            if has_context
            else self._build_no_context_prompt(normalized_question)
        )

        return BuiltPrompt(
            prompt=prompt,
            question=normalized_question,
            source_count=context.chunk_count,
            context_char_count=context.context_char_count,
            has_context=has_context,
        )

    def _build_context_prompt(self, question: str, context: BuiltContext) -> str:
        return ANSWER_GENERATION_PROMPT.format(
            assistant_role=self.assistant_role,
            no_context_message=self.no_context_message,
            source_scope=self._source_scope(context),
            context=context.prompt_context,
            question=question,
        )

    def _build_no_context_prompt(self, question: str) -> str:
        return NO_CONTEXT_ANSWER_PROMPT.format(
            assistant_role=self.assistant_role,
            no_context_message=self.no_context_message,
            question=question,
        )

    def _normalize_question(self, question: str) -> str:
        normalized = " ".join(question.split())

        if not normalized:
            raise ValueError("question must not be empty")

        return normalized

    def _source_scope(self, context: BuiltContext) -> str:
        source_count = len(context.sources)

        if source_count == 0:
            return "No retrieved papers are available."

        if source_count == 1:
            source = context.sources[0]
            return (
                "The retrieved context comes from 1 paper: "
                f'"{source.title}" (arXiv:{source.arxiv_id}).'
            )

        titles = ", ".join(
            f'"{source.title}" (arXiv:{source.arxiv_id})'
            for source in context.sources[:5]
        )

        if source_count > 5:
            titles = f"{titles}, and {source_count - 5} more paper(s)"

        return f"The retrieved context comes from {source_count} papers: {titles}."
