# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import date
from typing import Any

from rag.config import AgenticRAGSettings
from rag.service.elasticsearch.searching import SearchingService
from rag.service.llm import LLMGenerationSettings, LLMProvider
from rag.service.orchestration.prompts.agentic_prompt import (
    ANSWER_CRITIC_PROMPT,
    ANSWER_REPAIR_PROMPT,
    EVIDENCE_GRADER_PROMPT,
    FOLLOWUP_ROUTER_PROMPT,
    QUERY_REWRITE_PROMPT,
    SCOPE_ROUTER_PROMPT,
)
from rag.service.orchestration.utils import parse_json_object
from rag.service.orchestration.core.agentic.state import (
    AgenticRAGState,
    hits_from_state,
    hits_to_state,
)
from rag.service.orchestration.context_builder import ContextBuilder
from rag.service.orchestration.input_guardrails import InputGuardrails
from rag.service.orchestration.prompt_builder import PromptBuilder
from rag.service.reranker import RerankerProvider


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
    ) -> None:
        self.settings = settings
        self.searching_service = searching_service
        self.llm_provider = llm_provider
        self.reranker_provider = reranker_provider
        self.input_guardrails = input_guardrails or InputGuardrails(llm_provider)
        self.context_builder = context_builder or ContextBuilder()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.status_callback = status_callback
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
        self.repair_settings = LLMGenerationSettings(
            temperature=0.1,
            top_p=0.9,
            top_k=20,
            max_tokens=1024,
            num_ctx=4096,
        )

    async def input_guardrail(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Checking request safety...")

        question = " ".join(state["question"].split())
        guardrail = await self.input_guardrails.evaluate_user_query(question)

        base_update: dict[str, Any] = {
            "question": question,
            "original_query": question,
            "resolved_query": question,
            "rewritten_query": None,
            "blocked": not guardrail.allowed,
            "is_safe": guardrail.allowed,
            "is_in_scope": False,
            "is_followup": False,
            "requires_retrieval": True,
            "answer": "",
            "guardrail": guardrail.to_dict(),
            "scope": {},
            "followup": {},
            "retrieval_plan": {},
            "evidence_grade": {},
            "answer_critique": {},
            "search_hits": [],
            "reranked_hits": [],
            "context": {},
            "citations": [],
            "sources": [],
            "retrieval_attempts": 0,
            "answer_repair_attempts": 0,
            "errors": [],
            "metadata": {},
        }

        if not guardrail.allowed:
            return {
                **base_update,
                "answer": guardrail.response or "Sorry, I can't process that request.",
            }

        assert guardrail.safe_query is not None

        return {
            **base_update,
            "safe_query": guardrail.safe_query,
            "current_query": guardrail.safe_query,
        }

    async def scope_router(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Checking research scope...")

        question = state["safe_query"]
        fallback = self._fallback_scope(question)

        try:
            data = await self._structured_json(
                SCOPE_ROUTER_PROMPT.format(question=question),
                self.decision_settings,
            )

            decision = str(data.get("decision", fallback["decision"]))

            if decision not in {"retrieve", "direct_response", "out_of_scope"}:
                raise ValueError("invalid scope decision")

            scope = {
                "decision": decision,
                "confidence": float(data.get("confidence", fallback["confidence"])),
                "reason": str(data.get("reason", fallback["reason"])),
                "response": data.get("response"),
            }

        except Exception as error:
            scope = {**fallback, "fallback_error": str(error)}

        answer = ""

        if scope["decision"] == "direct_response":
            answer = str(
                scope.get("response")
                or (
                    "I can answer questions about indexed arXiv papers and cite "
                    "the retrieved sources."
                )
            )
        elif scope["decision"] == "out_of_scope":
            answer = str(
                scope.get("response")
                or (
                    "I can help with indexed arXiv paper questions, but that "
                    "request is outside my current scope."
                )
            )

        requires_retrieval = scope["decision"] == "retrieve"

        return {
            "scope": scope,
            "answer": answer,
            "is_in_scope": scope["decision"] != "out_of_scope",
            "requires_retrieval": requires_retrieval,
        }

    async def followup_router(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Resolving conversation context...")

        question = state["safe_query"]
        fallback = self._fallback_followup(state)

        if not self.settings.enable_followup_context:
            followup = {
                **fallback,
                "route": "new_retrieval",
                "reason": "Follow-up context is disabled.",
            }
        else:
            try:
                data = await self._structured_json(
                    FOLLOWUP_ROUTER_PROMPT.format(
                        question=question,
                        conversation_context=self._format_conversation_context(
                            state.get("conversation_context", [])
                        ),
                    ),
                    self.decision_settings,
                )

                resolved_query = " ".join(
                    str(data.get("resolved_query") or question).split()
                )
                requires_retrieval = bool(data.get("requires_retrieval", True))
                reuse_previous_evidence = bool(
                    data.get("reuse_previous_evidence", False)
                )

                route = (
                    "use_active_context"
                    if reuse_previous_evidence and state.get("active_hits", [])
                    else "new_retrieval"
                )

                followup = {
                    "route": route,
                    "is_followup": bool(data.get("is_followup", False)),
                    "resolved_query": resolved_query or question,
                    "requires_retrieval": requires_retrieval,
                    "reuse_previous_evidence": reuse_previous_evidence,
                    "reason": str(data.get("reason", "LLM follow-up routing")),
                }

            except Exception as error:
                followup = {**fallback, "fallback_error": str(error)}

        return {
            "followup": followup,
            "is_followup": bool(followup.get("is_followup", False)),
            "requires_retrieval": bool(followup.get("requires_retrieval", True)),
            "resolved_query": str(followup.get("resolved_query") or question),
            "current_query": str(followup.get("resolved_query") or question),
        }

    async def prepare_retrieval(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Preparing retrieval...")

        query = state.get("resolved_query") or state["current_query"]
        lower_query = query.lower()

        retrieval_mode = state.get("retrieval_mode") or "hybrid"
        top_k = int(state.get("top_k") or self.settings.default_top_k)
        candidate_pool_size = int(
            state.get("candidate_pool_size")
            or self.settings.default_candidate_pool_size
        )
        candidate_pool_size = max(candidate_pool_size, top_k)
        latest_first = bool(
            state.get("latest_first")
            or any(word in lower_query for word in ["latest", "newest", "recent"])
        )
        include_highlights = bool(
            state.get("include_highlights") or retrieval_mode in {"bm25", "hybrid"}
        )
        fuzziness = state.get("fuzziness")

        if fuzziness is None and any(
            word in lower_query for word in ["title", "called"]
        ):
            fuzziness = "AUTO"

        plan = {
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

        return {
            "retrieval_plan": plan,
        }

    async def retrieve(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Retrieving documents...")

        plan = state["retrieval_plan"]
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
            errors = list(state.get("errors", []))
            errors.append(f"retrieve failed: {error}")
            return {
                "retrieval_attempts": attempts,
                "search_hits": [],
                "reranked_hits": [],
                "errors": errors,
            }

    async def rerank(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Reranking evidence...")

        plan = state["retrieval_plan"]
        hits = hits_from_state(state.get("search_hits", []))

        if not plan.get("use_reranker"):
            return {
                "reranked_hits": [],
            }

        if self.reranker_provider is None:
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
                top_k=int(plan["top_k"]),
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
            errors = list(state.get("errors", []))
            errors.append(f"reranker failed; using original search order: {error}")
            return {
                "reranked_hits": [],
                "errors": errors,
            }

    async def build_context(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Building citation context...")

        if state.get("followup", {}).get("route") == "use_active_context":
            hit_values = state.get("active_hits", [])
        else:
            hit_values = state.get("reranked_hits") or state.get("search_hits", [])

        hits = hits_from_state(hit_values)
        top_k = int(
            state.get("retrieval_plan", {}).get("top_k", self.settings.default_top_k)
        )

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
            "active_hits": hits_to_state(hits[:top_k]),
        }

    async def evidence_grader(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Checking evidence quality...")

        context = state.get("context", {})
        context_prompt = str(context.get("context_prompt", ""))
        fallback = self._fallback_evidence_grade(state)

        if not context_prompt.strip():
            grade = fallback
        else:
            try:
                data = await self._structured_json(
                    EVIDENCE_GRADER_PROMPT.format(
                        question=state.get("resolved_query") or state["safe_query"],
                        context=self._truncate(context_prompt, 6_000),
                    ),
                    self.decision_settings,
                )
                grade_name = str(data.get("grade", fallback["grade"]))
                if grade_name not in {"strong", "weak", "none"}:
                    raise ValueError("invalid evidence grade")

                grade = {
                    "grade": grade_name,
                    "score": float(data.get("score", fallback["score"])),
                    "reason": str(data.get("reason", fallback["reason"])),
                }

            except Exception as error:
                grade = {**fallback, "fallback_error": str(error)}

        return {
            "evidence_grade": grade,
        }

    async def rewrite_query(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Refining search query...")
        evidence = state.get("evidence_grade", {})
        fallback_query = self._fallback_rewrite_query(state)

        try:
            data = await self._structured_json(
                QUERY_REWRITE_PROMPT.format(
                    question=state.get("resolved_query") or state["safe_query"],
                    current_query=state["current_query"],
                    evidence_reason=evidence.get("reason", "weak evidence"),
                ),
                self.rewrite_settings,
            )
            query = " ".join(str(data.get("query", fallback_query)).split())
            if not query:
                raise ValueError("empty rewritten query")

        except Exception:
            query = fallback_query

        return {
            "current_query": query,
            "rewritten_query": query,
        }

    async def no_context_fallback(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Preparing insufficient-evidence response...")
        return {
            "answer": "The indexed sources are insufficient to answer this question.",
        }

    async def answer_generator(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Generating answer...")

        context_data = state.get("context", {})
        requires_retrieval = bool(state.get("requires_retrieval", True))
        has_context = bool(str(context_data.get("context_prompt", "")).strip())

        if requires_retrieval and not has_context:
            return await self.no_context_fallback(state)

        if not has_context:
            generation = await self.llm_provider.generate(
                prompt=self._build_direct_answer_prompt(state),
                settings=self.answer_settings,
            )

            metadata = {
                **state.get("metadata", {}),
                "answer_model": generation.model_name,
                "answer_usage": asdict(generation.usage),
            }

            return {
                "answer": generation.response_text,
                "metadata": metadata,
            }

        built_prompt = self.prompt_builder.build_prompt(
            question=state.get("resolved_query") or state["safe_query"],
            context=self._context_from_state(context_data),
        )

        prompt = self._inject_conversation_context(
            prompt=built_prompt.prompt,
            conversation_context=state.get("conversation_context", []),
        )

        generation = await self.llm_provider.generate(
            prompt=prompt,
            settings=self.answer_settings,
        )

        metadata = {
            **state.get("metadata", {}),
            "answer_model": generation.model_name,
            "answer_usage": asdict(generation.usage),
        }

        return {
            "answer": generation.response_text,
            "metadata": metadata,
        }

    async def answer_critic(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Reviewing answer...")

        citation_verification = self._verify_citations(state)

        if not self.settings.enable_answer_critique:
            critique = self._passing_critique("answer critique disabled")
        else:
            fallback = self._fallback_answer_critique(citation_verification)

            try:
                data = await self._structured_json(
                    ANSWER_CRITIC_PROMPT.format(
                        question=state.get("resolved_query") or state["safe_query"],
                        context=self._truncate(
                            str(state.get("context", {}).get("context_prompt", "")),
                            6_000,
                        ),
                        answer=state.get("answer", ""),
                        citation_verification=json.dumps(
                            citation_verification,
                            ensure_ascii=True,
                        ),
                    ),
                    self.decision_settings,
                )

                verdict = str(data.get("verdict", fallback["verdict"]))

                if verdict not in {"pass", "repair", "fail"}:
                    raise ValueError("invalid critique verdict")

                critique = {
                    "verdict": verdict,
                    "groundedness_score": float(
                        data.get("groundedness_score", fallback["groundedness_score"])
                    ),
                    "citation_score": float(
                        data.get("citation_score", fallback["citation_score"])
                    ),
                    "completeness_score": float(
                        data.get("completeness_score", fallback["completeness_score"])
                    ),
                    "issues": self._string_list(data.get("issues", [])),
                    "unsupported_claims": self._string_list(
                        data.get("unsupported_claims", [])
                    ),
                    "suggested_fix": data.get("suggested_fix"),
                }

            except Exception as error:
                critique = {**fallback, "fallback_error": str(error)}

        return {
            "answer_critique": critique,
        }

    async def answer_repair(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Repairing answer...")

        attempts = int(state.get("answer_repair_attempts", 0)) + 1
        prompt = ANSWER_REPAIR_PROMPT.format(
            question=state.get("resolved_query") or state["safe_query"],
            context=state.get("context", {}).get("context_prompt", ""),
            answer=state.get("answer", ""),
            critique=json.dumps(state.get("answer_critique", {}), ensure_ascii=True),
        )

        generation = await self.llm_provider.generate(
            prompt=prompt,
            settings=self.repair_settings,
        )

        metadata = {
            **state.get("metadata", {}),
            "answer_model": generation.model_name,
            "answer_usage": asdict(generation.usage),
        }

        return {
            "answer": generation.response_text,
            "answer_repair_attempts": attempts,
            "metadata": metadata,
        }

    async def targeted_retrieval(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Retrieving targeted evidence...")

        query = self._fallback_rewrite_query(state)

        return {
            "current_query": query,
            "rewritten_query": query,
        }

    async def save_thread_state(self, state: AgenticRAGState) -> dict[str, Any]:
        await self._emit_status("Saving conversation state...")
        return {}

    def _fallback_scope(self, question: str) -> dict[str, Any]:
        lower = question.lower()

        direct_markers = ["what can you do", "help", "how do i ask", "who are you"]
        out_markers = ["recipe", "weather", "stock price", "travel itinerary"]

        if any(marker in lower for marker in direct_markers):
            return {
                "decision": "direct_response",
                "confidence": 0.7,
                "reason": "Capability/help question.",
                "response": (
                    "I can answer questions about indexed arXiv papers and cite "
                    "the retrieved sources."
                ),
            }

        if any(marker in lower for marker in out_markers):
            return {
                "decision": "out_of_scope",
                "confidence": 0.7,
                "reason": "Question is unrelated to indexed arXiv paper retrieval.",
                "response": (
                    "I can help with indexed arXiv paper questions, but that "
                    "request is outside my current scope."
                ),
            }

        return {
            "decision": "retrieve",
            "confidence": 0.6,
            "reason": "Question may be answerable from indexed papers.",
            "response": None,
        }

    def _fallback_followup(self, state: AgenticRAGState) -> dict[str, Any]:
        question = state["safe_query"]
        lower_question = question.lower()
        active_hits = state.get("active_hits", [])
        has_context = bool(state.get("conversation_context", []))
        followup_markers = [
            "source",
            "previous",
            "above",
            "top",
            "second",
            "third",
            "them",
            "those",
            "compare",
            "which one",
            "explain it",
            "explain this",
            "what about",
        ]

        is_followup = has_context and any(
            marker in lower_question for marker in followup_markers
        )
        reuse_previous_evidence = is_followup and bool(active_hits)
        route = "use_active_context" if reuse_previous_evidence else "new_retrieval"

        return {
            "route": route,
            "is_followup": is_followup,
            "resolved_query": question,
            "requires_retrieval": True,
            "reuse_previous_evidence": reuse_previous_evidence,
            "reason": (
                "Question appears to refer to previous evidence."
                if is_followup
                else "Question needs a fresh retrieval pass."
            ),
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

    def _fallback_answer_critique(
        self,
        verification: dict[str, Any],
    ) -> dict[str, Any]:
        if not verification.get("valid", True):
            return {
                "verdict": "repair",
                "groundedness_score": 0.55,
                "citation_score": 0.2,
                "completeness_score": 0.5,
                "issues": ["Citation verification failed."],
                "unsupported_claims": [],
                "suggested_fix": (
                    "Repair the answer so every factual claim cites valid sources."
                ),
            }

        return self._passing_critique("deterministic citation checks passed")

    def _passing_critique(self, reason: str) -> dict[str, Any]:
        return {
            "verdict": "pass",
            "groundedness_score": 0.8,
            "citation_score": 0.9,
            "completeness_score": 0.75,
            "issues": [reason],
            "unsupported_claims": [],
            "suggested_fix": None,
        }

    def _fallback_rewrite_query(self, state: AgenticRAGState) -> str:
        pieces = [state.get("original_query") or state.get("safe_query", "")]
        active_paper_ids = [
            str(source["paper_id"])
            for source in state.get("sources", [])
            if source.get("paper_id")
        ]

        if active_paper_ids:
            pieces.append(" ".join(active_paper_ids[:3]))

        pieces.append("method experiment result evaluation benchmark")
        return " ".join(piece for piece in pieces if piece).strip()

    async def _structured_json(
        self,
        prompt: str,
        settings: LLMGenerationSettings,
    ) -> dict[str, Any]:
        generation = await self.llm_provider.generate(prompt=prompt, settings=settings)
        return parse_json_object(generation.response_text)

    async def _emit_status(self, text: str) -> None:
        if self.status_callback is not None:
            await self.status_callback(text)

    def _context_from_state(self, data: dict[str, Any]):
        from rag.service.orchestration.context_builder import (
            Citation,
            PaperMetadata,
            RetrievalContext,
            Source,
        )

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

    def _build_direct_answer_prompt(self, state: AgenticRAGState) -> str:
        conversation_context = self._format_conversation_context(
            state.get("conversation_context", [])
        )
        query = state.get("resolved_query") or state["safe_query"]

        return "\n".join(
            [
                "# Role",
                "You are an arXiv paper research assistant.",
                "",
                "# Rules",
                (
                    "- Answer the current user message using only the recent "
                    "conversation context."
                ),
                "- If the conversation context is insufficient, say so briefly.",
                "- Do not invent paper evidence or citations.",
                "",
                "# Recent Conversation Context",
                conversation_context,
                "",
                "# Current User Message",
                query,
                "",
                "# Answer",
            ]
        )

    def _verify_citations(self, state: AgenticRAGState) -> dict[str, Any]:
        answer = state.get("answer", "")
        valid_numbers = {
            int(citation["source_number"]) for citation in state.get("citations", [])
        }
        cited_numbers = sorted(
            {
                int(match)
                for match in re.findall(r"\[Source\s+(\d+)\]", answer, re.IGNORECASE)
            }
        )
        invalid_numbers = [
            source_number
            for source_number in cited_numbers
            if source_number not in valid_numbers
        ]
        missing_citations = bool(state.get("citations")) and not cited_numbers

        return {
            "valid": not invalid_numbers and not missing_citations,
            "cited_source_numbers": cited_numbers,
            "invalid_source_numbers": invalid_numbers,
            "missing_citations": missing_citations,
            "available_source_numbers": sorted(valid_numbers),
        }

    def _parse_date(self, value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value

        return date.fromisoformat(str(value))

    def _truncate(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text

        return text[:max_chars].rstrip() + "..."

    def _string_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []

        return [str(value) for value in values]
