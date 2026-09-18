# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import date
from typing import Any

from rag.config import AgenticRAGSettings
from rag.service.elasticsearch.searching import SearchingService
from rag.service.llm import LLMGenerationSettings, LLMProvider
from rag.service.orchestration.prompts.agentic_prompt import (
    EVIDENCE_GRADER_PROMPT,
    QUERY_REWRITE_PROMPT,
    SCOPE_ROUTER_PROMPT,
)
from rag.service.orchestration.utils import parse_json_object
from rag.service.orchestration.core.agentic.state import (
    AgenticRAGState,
    hits_from_state,
    hits_to_state,
)
from rag.service.orchestration.context_builder import (
    Citation,
    ContextBuilder,
    PaperMetadata,
    RetrievalContext,
    Source,
)
from rag.service.orchestration.input_guardrails import InputGuardrails
from rag.service.orchestration.prompt_builder import PromptBuilder
from rag.service.reranker import RerankerProvider


logger = logging.getLogger(__name__)


class AgenticRAGNodes:
    def __init__(
        self,
        settings: AgenticRAGSettings,
        searching_service: SearchingService,
        llm_provider: LLMProvider,
        reranker_provider: RerankerProvider | None,
        input_guardrails: InputGuardrails | None = None,
        context_builder: ContextBuilder | None = None,
        prompt_builder: PromptBuilder | None = None,
        status_callback: Callable[[str], Awaitable[None]] | None = None,
        answer_fragment_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.settings = settings
        self.searching_service = searching_service
        self.llm_provider = llm_provider
        self.reranker_provider = reranker_provider
        self.input_guardrails = input_guardrails or InputGuardrails(llm_provider)
        self.context_builder = context_builder or ContextBuilder()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.status_callback = status_callback
        self.answer_fragment_callback = answer_fragment_callback
        self.decision_settings = LLMGenerationSettings(
            temperature=0.0,
            top_p=1.0,
            top_k=1,
            repeat_penalty=1.0,
            max_tokens=384,
            num_ctx=4096,
            response_format="json",
        )
        self.rewrite_settings = LLMGenerationSettings(
            temperature=0.1,
            top_p=0.9,
            top_k=20,
            max_tokens=192,
            num_ctx=4096,
            response_format="json",
        )
        self.answer_settings = LLMGenerationSettings()

    async def input_guardrail(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Reading user request...")

        question = " ".join(state["question"].split())
        guardrail = await self.input_guardrails.evaluate_user_query(question)

        fresh_state: dict[str, Any] = {
            "question": question,
            "resolved_query": question,
            "rewritten_query": None,
            "blocked": not guardrail.allowed,
            "answer": "",
            "guardrail": guardrail.to_dict(),
            "scope": {},
            "evidence_grade": {},
            "search_hits": [],
            "reranked_hits": [],
            "context": {},
            "citations": [],
            "sources": [],
            "retrieval_attempts": 0,
            "errors": [],
            "metadata": {},
        }

        if not guardrail.allowed:
            return {
                **fresh_state,
                "answer": self._blocked_response(),
            }

        safe_query = (
            guardrail.safe_query or question
        )  # use initial question if safe query does not exist

        return {
            **fresh_state,
            "safe_query": safe_query,
            "current_query": safe_query,
        }

    async def scope_router(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Thinking...")

        question = state["safe_query"]
        fallback = self._fallback_scope(state)

        try:
            prompt = SCOPE_ROUTER_PROMPT.format(
                question=question,
                conversation_context=self._format_conversation_context(
                    state.get("conversation_context", [])
                ),
            )

            llm_response = await self._generate_llm_json_response(
                prompt,
                generation_settings=self.decision_settings,
            )

            decision = str(llm_response.get("decision", fallback["decision"]))

            if decision not in {"retrieve", "direct_response", "out_of_scope"}:
                raise ValueError("invalid scope decision")

            resolved_query = " ".join(
                str(llm_response.get("resolved_query") or question).split()
            )

            scope = {
                "decision": decision,
                "confidence": float(
                    llm_response.get("confidence", fallback["confidence"])
                ),
                "reason": str(llm_response.get("reason", fallback["reason"])),
                "response": llm_response.get("response"),
                "resolved_query": resolved_query or question,
                "conversation_title": self._safe_conversation_title(
                    llm_response.get("conversation_title")
                ),
            }

        except Exception as error:
            logger.warning(
                "Agentic scope routing failed; using fallback",
                exc_info=True,
            )
            scope = {
                **fallback,
                "fallback_error": str(error),
            }

        answer = ""

        if scope["decision"] == "direct_response":
            answer = self._safe_direct_response(
                scope.get("response"),
                fallback=self._direct_response(),
            )
        elif scope["decision"] == "out_of_scope":
            answer = self._safe_direct_response(
                scope.get("response"),
                fallback=self._out_of_scope_response(),
            )

        metadata = state.get("metadata", {})
        conversation_title = scope.get("conversation_title")

        if conversation_title:
            metadata = {
                **metadata,
                "conversation_title": conversation_title,
            }

        return {
            "scope": scope,
            "answer": answer,
            "resolved_query": str(scope.get("resolved_query") or question),
            "current_query": str(scope.get("resolved_query") or question),
            "metadata": metadata,
        }

    async def retrieve(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Searching related documents...")

        plan = self._build_retrieval_plan(state)
        use_reranker = bool(plan["use_reranker"])
        size = plan["candidate_pool_size"] if use_reranker else plan["top_k"]
        attempts = int(state.get("retrieval_attempts", 0)) + 1

        try:
            result = await self.searching_service.search(
                query=str(plan["query"]),
                mode=plan["retrieval_mode"],
                size=size,
                offset=0,
                candidate_pool_size=plan["candidate_pool_size"],
                num_candidates=plan.get("num_candidates"),
                categories=plan.get("categories"),
                paper_id=plan.get("paper_id"),
                published_from=self._parse_date(plan.get("published_from")),
                published_to=self._parse_date(plan.get("published_to")),
                latest_first=bool(plan.get("latest_first", False)),
                min_score=plan.get("min_score"),
                track_total_hits=bool(plan.get("track_total_hits", True)),
                fuzziness=plan.get("fuzziness"),
                include_highlights=bool(plan.get("include_highlights", True)),
            )

            metadata = {
                **state.get("metadata", {}),
                "last_total_hits": result.total,
                "last_search_candidates": len(result.results),
            }

            return {
                "retrieval_attempts": attempts,
                "search_hits": hits_to_state(result.results),
                "reranked_hits": [],
                "metadata": metadata,
            }

        except Exception as error:
            logger.warning(
                "Agentic retrieval failed: query=%r mode=%s attempt=%s",
                plan["query"],
                plan["retrieval_mode"],
                attempts,
                exc_info=True,
            )
            errors = list(state.get("errors", []))
            errors.append(f"retrieve failed: {error}")
            return {
                "retrieval_attempts": attempts,
                "search_hits": [],
                "reranked_hits": [],
                "errors": errors,
            }

    async def rerank(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Ranking evidence...")

        hits = hits_from_state(state.get("search_hits", []))
        use_reranker = bool(
            state.get("use_reranker", self.settings.use_reranker_by_default)
        )
        top_k = int(state.get("top_k") or self.settings.default_top_k)

        if not use_reranker:
            return {
                "reranked_hits": [],
            }

        if self.reranker_provider is None:
            logger.warning(
                "Agentic reranker requested but provider is not initialized"
            )
            errors = list(state.get("errors", []))
            errors.append("reranker requested but provider is not initialized")
            return {
                "reranked_hits": [],
                "errors": errors,
            }

        try:
            result = await self.reranker_provider.rerank(
                query=state["current_query"],
                chunks=hits,
                top_k=top_k,
            )

            metadata = {
                **state.get("metadata", {}),
                "reranker_model": result.model_name,
                "reranker_latency_ms": result.latency_ms,
            }

            return {
                "reranked_hits": hits_to_state(result.hits()),
                "metadata": metadata,
            }

        except Exception as error:
            logger.warning(
                "Agentic reranker failed; using original search order",
                exc_info=True,
            )
            errors = list(state.get("errors", []))
            errors.append(f"reranker failed; using original search order: {error}")
            return {
                "reranked_hits": [],
                "errors": errors,
            }

    async def build_context(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Building citation...")

        hit_values = state.get("reranked_hits") or state.get("search_hits", [])
        hits = hits_from_state(hit_values)
        top_k = int(state.get("top_k") or self.settings.default_top_k)

        context = self.context_builder.build_context(hits[:top_k])
        context_data = {
            **context.to_dict(),
            "chunk_count": len(context.citations),
            "context_char_count": context.context_size,
        }
        citations = [citation.to_dict() for citation in context.citations]
        sources = [source.to_dict() for source in context.sources]

        return {
            "context": context_data,
            "citations": citations,
            "sources": sources,
        }

    async def evidence_grader(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Validating evidence...")

        context = state.get("context", {})
        context_prompt = str(context.get("context_prompt", ""))
        fallback = self._fallback_evidence_grade(state)

        if not context_prompt.strip():
            grade = fallback
        else:
            try:
                prompt = EVIDENCE_GRADER_PROMPT.format(
                    question=state.get("resolved_query") or state["safe_query"],
                    context=self._truncate(context_prompt, 6_000),
                )

                llm_response = await self._generate_llm_json_response(
                    prompt,
                    generation_settings=self.decision_settings,
                )

                grade_name = str(llm_response.get("grade", fallback["grade"]))

                if grade_name not in {"strong", "weak", "none"}:
                    raise ValueError("invalid evidence grade")

                grade = {
                    "grade": grade_name,
                    "score": float(llm_response.get("score", fallback["score"])),
                    "reason": str(llm_response.get("reason", fallback["reason"])),
                }

            except Exception as error:
                logger.warning(
                    "Agentic evidence grading failed; using fallback grade",
                    exc_info=True,
                )
                grade = {**fallback, "fallback_error": str(error)}

        return {
            "evidence_grade": grade,
        }

    async def rewrite_query(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Refining user question...")

        evidence = state.get("evidence_grade", {})
        fallback_query = self._fallback_rewrite_query(state)

        try:
            prompt = QUERY_REWRITE_PROMPT.format(
                question=state.get("resolved_query") or state["safe_query"],
                current_query=state["current_query"],
                evidence_reason=evidence.get("reason", "weak evidence"),
            )

            llm_response = await self._generate_llm_json_response(
                prompt,
                generation_settings=self.rewrite_settings,
            )

            query = " ".join(str(llm_response.get("query", fallback_query)).split())

            if not query:
                raise ValueError("empty rewritten query")

        except Exception:
            logger.warning(
                "Agentic query rewrite failed; using fallback query",
                exc_info=True,
            )
            query = fallback_query

        return {
            "current_query": query,
            "rewritten_query": query,
        }

    async def no_context_fallback(self, state: AgenticRAGState) -> dict[str, Any]:
        return {
            "answer": "The indexed sources are insufficient to answer this question.",
        }

    def _blocked_response(self) -> str:
        return (
            "Sorry, I can't process that request. I can help with questions "
            "about indexed arXiv papers."
        )

    def _direct_response(self) -> str:
        return (
            "Hi, I am your arXiv research assistant. Ask me about indexed "
            "papers, methods, datasets, results, citations, or comparisons, "
            "and I will answer from the available paper context."
        )

    def _out_of_scope_response(self) -> str:
        return (
            "I can help with indexed arXiv paper questions, but that request is "
            "outside my current scope."
        )

    def _safe_direct_response(self, value: Any, fallback: str) -> str:
        if not isinstance(value, str):
            return fallback

        response = " ".join(value.split())

        if not response:
            return fallback

        lowered = response.lower()
        blocked_terms = (
            "classifier",
            "guardrail",
            "scope router",
            "router",
            "system prompt",
            "developer prompt",
            "hidden prompt",
            "policy",
            "workflow",
        )

        if any(term in lowered for term in blocked_terms):
            return fallback

        return response

    def _safe_conversation_title(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None

        title = " ".join(value.split()).strip(" .,:;-'\"")

        if not title:
            return None

        words = title.split()

        if len(words) > 7:
            title = " ".join(words[:7])

        if len(title) > 72:
            title = title[:72].rstrip()

        lowered = title.lower()

        if lowered in {"chat", "conversation", "research discussion"}:
            return None

        return title

    async def answer_generator(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Writing answer...")

        context_data = state.get("context", {})
        has_context = bool(str(context_data.get("context_prompt", "")).strip())

        if not has_context:
            return await self.no_context_fallback(state)

        built_prompt = self.prompt_builder.build_prompt(
            question=state.get("resolved_query") or state["safe_query"],
            context=self._context_from_state(context_data),
        )

        prompt = self._inject_conversation_context(
            prompt=built_prompt.prompt,
            conversation_context=state.get("conversation_context", []),
        )

        answer_parts: list[str] = []

        async for chunk in self.llm_provider.stream(
            prompt=prompt,
            settings=self.answer_settings,
        ):
            answer_parts.append(chunk)
            await self._emit_answer_fragment(chunk)

        answer = "".join(answer_parts)
        usage = getattr(self.llm_provider, "last_stream_usage", None)

        metadata = {
            **state.get("metadata", {}),
            "answer_model": self.llm_provider.model_name,
        }

        if usage is not None:
            metadata["answer_usage"] = asdict(usage)

        return {
            "answer": answer,
            "metadata": metadata,
        }

    async def save_thread_state(self, state: AgenticRAGState) -> dict[str, Any]:
        return {}

    def _build_retrieval_plan(self, state: AgenticRAGState) -> dict[str, Any]:
        query = (
            state.get("current_query")
            or state.get("resolved_query")
            or state["safe_query"]
        )
        lower_query = query.lower()

        retrieval_mode = state.get("retrieval_mode") or "hybrid"

        top_k = int(state.get("top_k") or self.settings.default_top_k)
        candidate_pool_size = int(
            state.get("candidate_pool_size")
            or self.settings.default_candidate_pool_size
        )
        candidate_pool_size = max(candidate_pool_size, top_k)

        # NOTE: rule-based assumption when user mention
        latest_first = bool(
            state.get("latest_first")
            or any(word in lower_query for word in ["latest", "newest", "recent"])
        )
        include_highlights = bool(state.get("include_highlights", False))

        fuzziness = state.get("fuzziness")

        # NOTE: rule-based assumption when user mention
        if fuzziness is None and any(
            word in lower_query for word in ["title", "called"]
        ):
            fuzziness = "AUTO"

        return {
            "query": query,
            "retrieval_mode": retrieval_mode,
            "top_k": top_k,
            "candidate_pool_size": candidate_pool_size,
            "use_reranker": bool(
                state.get("use_reranker", self.settings.use_reranker_by_default)
            ),
            "num_candidates": state.get("num_candidates"),
            "categories": state.get("categories"),
            "paper_id": state.get("paper_id"),
            "published_from": state.get("published_from"),
            "published_to": state.get("published_to"),
            "latest_first": latest_first,
            "min_score": state.get("min_score"),
            "track_total_hits": state.get("track_total_hits", True),
            "include_highlights": include_highlights,
            "fuzziness": fuzziness,
        }

    def _fallback_scope(self, state: AgenticRAGState) -> dict[str, Any]:
        question = state["safe_query"]

        return {
            "decision": "retrieve",
            "confidence": 0.0,
            "reason": "Scope routing failed; defaulting to retrieval.",
            "response": None,
            "resolved_query": question,
        }

    def _fallback_evidence_grade(self, state: AgenticRAGState) -> dict[str, Any]:
        chunk_count = int(state.get("context", {}).get("chunk_count", 0))

        if chunk_count == 0:
            return {
                "grade": "none",
                "score": 0.0,
                "reason": "No retrieved context was available.",
            }

        if chunk_count < self.settings.weak_evidence_min_chunks:
            return {
                "grade": "weak",
                "score": 0.4,
                "reason": "Too few chunks were retrieved for a confident answer.",
            }

        return {
            "grade": "strong",
            "score": 0.75,
            "reason": "Retrieved context contains enough chunks for answer generation.",
        }

    def _fallback_rewrite_query(self, state: AgenticRAGState) -> str:
        return (
            state.get("resolved_query")
            or state.get("current_query")
            or state.get("safe_query", "")
        )

    async def _generate_llm_json_response(
        self,
        prompt: str,
        generation_settings: LLMGenerationSettings,
    ) -> dict[str, Any]:
        """
        Generate response from LLM and returned response is expected to be a valid JSON
        """
        generation = await self.llm_provider.generate(
            prompt=prompt, settings=generation_settings
        )
        return parse_json_object(generation.response_text)

    async def _emit_status(self, text: str) -> None:
        if self.status_callback is not None:
            await self.status_callback(text)

    async def _emit_answer_fragment(self, text: str) -> None:
        if self.answer_fragment_callback is not None:
            await self.answer_fragment_callback(text)

    def _context_from_state(self, data: dict[str, Any]):
        return RetrievalContext(
            context_prompt=str(data.get("context_prompt", "")),
            citations=[
                Citation(
                    source_number=int(citation["source_number"]),
                    chunk_id=str(citation["chunk_id"]),
                    paper_metadata=PaperMetadata(
                        paper_id=str(citation["paper_id"]),
                        arxiv_id=str(citation["arxiv_id"]),
                        title=str(citation["title"]),
                        authors=[str(value) for value in citation.get("authors", [])],
                        categories=[
                            str(value) for value in citation.get("categories", [])
                        ],
                        published_date=str(citation.get("published_date", "")),
                        pdf_url=str(citation["pdf_url"]),
                        pdf_storage_key=citation.get("pdf_storage_key"),
                    ),
                    section_title=citation.get("section_title"),
                    chunk_index=int(citation["chunk_index"]),
                    score=citation.get("score"),
                    highlights=[str(value) for value in citation.get("highlights", [])],
                    source_storage_key=citation.get("source_storage_key"),
                    start_char=citation.get("start_char"),
                    end_char=citation.get("end_char"),
                )
                for citation in data.get("citations", [])
            ],
            sources=[
                Source(
                    paper_source_number=int(source["paper_source_number"]),
                    paper_metadata=PaperMetadata(
                        paper_id=str(source["paper_id"]),
                        arxiv_id=str(source["arxiv_id"]),
                        title=str(source["title"]),
                        authors=[str(value) for value in source.get("authors", [])],
                        categories=[
                            str(value) for value in source.get("categories", [])
                        ],
                        published_date=str(source.get("published_date", "")),
                        pdf_url=str(source["pdf_url"]),
                        pdf_storage_key=source.get("pdf_storage_key"),
                    ),
                    citation_numbers=[
                        int(value) for value in source.get("citation_numbers", [])
                    ],
                )
                for source in data.get("sources", [])
            ],
            context_size=int(
                data.get("context_size", data.get("context_char_count", 0))
            ),
        )

    def _format_conversation_context(
        self,
        messages: list[dict[str, Any]],
        max_messages: int = 8,
        max_chars: int = 2_500,
    ) -> str:
        if not messages:
            return "No previous conversation."

        lines: list[str] = []

        for message in messages[-max_messages:]:
            role = str(message.get("role", "message")).title()
            content = " ".join(str(message.get("content", "")).split())

            if not content:
                continue

            lines.append(f"{role}: {self._truncate(content, 500)}")

        text = "\n".join(lines).strip()

        return self._truncate(text, max_chars) if text else "No previous conversation."

    def _inject_conversation_context(
        self,
        prompt: str,
        conversation_context: list[dict[str, Any]],
    ) -> str:
        formatted_context = self._format_conversation_context(conversation_context)

        if formatted_context == "No previous conversation.":
            return prompt

        insertion = "# Recent Conversation Context\n" f"{formatted_context}\n\n"
        marker = "# User Question"

        if marker in prompt:
            return prompt.replace(marker, insertion + marker, 1)

        return f"{insertion}{prompt}"

    def _parse_date(self, value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value

        return date.fromisoformat(str(value))

    def _truncate(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text

        return text[:max_chars].rstrip() + "..."
