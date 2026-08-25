# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from typing import Any

from rag.service.orchestration.context_builder import RetrievalContext
from rag.service.orchestration.prompts import (
    CONTEXT_GENERATION_PROMPT_V1,
    NO_CONTEXT_GENERATION_PROMPT_V1,
)


@dataclass(frozen=True, slots=True)
class FinalPrompt:
    """
    Response schema of the final prompt that are given to the LLMs,
    built from `PromptBuilder` class
    """

    prompt: str
    question: str
    source_count: int
    context_size: int
    has_context: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "question": self.question,
            "source_count": self.source_count,
            "context_size": self.context_size,
            "has_context": self.has_context,
        }


class QuestionValidationError(ValueError):
    """Raised when a prompt cannot be built from an empty question."""


class PromptBuilder:
    """
    Builds generation prompts from a user question and retrieved context,
    through `build_prompt()` method.
    """

    def __init__(
        self,
        assistant_role: str = "You are an arXiv paper research assistant.",
        no_context_message: str = (
            "The indexed sources are insufficient to answer this question."
        ),
    ) -> None:
        self.assistant_role = assistant_role
        self.no_context_message = no_context_message

    def build_prompt(self, question: str, context: RetrievalContext) -> FinalPrompt:
        """
        Normalize the question and assemble the final LLM prompt.

        Raises:
            QuestionValidationError: 
                If the question is empty after whitespace normalization.
        """

        normalized_question = self._normalize_question(question)
        has_context = bool(context.context_prompt.strip())

        prompt = (
            self._build_context_prompt(normalized_question, context)
            if has_context
            else self._build_no_context_prompt(normalized_question)
        )

        return FinalPrompt(
            prompt=prompt,
            question=normalized_question,
            source_count=len(context.citations),
            context_size=context.context_size,
            has_context=has_context,
        )

    def _build_context_prompt(self, question: str, context: RetrievalContext) -> str:
        return CONTEXT_GENERATION_PROMPT_V1.format(
            assistant_role=self.assistant_role,
            no_context_message=self.no_context_message,
            source_scope=self._source_scope(context),
            context=context.context_prompt,
            question=question,
        )

    def _build_no_context_prompt(self, question: str) -> str:
        return NO_CONTEXT_GENERATION_PROMPT_V1.format(
            assistant_role=self.assistant_role,
            no_context_message=self.no_context_message,
            question=question,
        )

    def _normalize_question(self, question: str) -> str:
        normalized = " ".join(question.split())

        if not normalized:
            raise QuestionValidationError("question must not be empty")

        return normalized

    def _source_scope(self, context: RetrievalContext) -> str:
        source_count = len(context.sources)

        if source_count == 0:
            return "No retrieved papers are available."

        if source_count == 1:
            paper_metadata = context.sources[0].paper_metadata
            return (
                "The retrieved context comes from 1 paper: "
                f'"{paper_metadata.title}" (arXiv:{paper_metadata.arxiv_id}).'
            )

        titles = ", ".join(
            f'"{source.paper_metadata.title}" (arXiv:{source.paper_metadata.arxiv_id})'
            for source in context.sources[:5]
        )

        if source_count > 5:
            titles = f"{titles}, and {source_count - 5} more paper(s)"

        return f"The retrieved context comes from {source_count} papers: {titles}."
