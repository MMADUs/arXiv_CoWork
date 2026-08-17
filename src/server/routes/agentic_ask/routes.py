# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import APIRouter, Depends, HTTPException, status

from rag.config import get_settings
from rag.service.elasticsearch.config.client import ElasticsearchClient
from rag.service.elasticsearch.searching import SearchingService
from rag.service.embedding.config.interface import EmbeddingProvider
from rag.service.llm.interface import LLMProvider
from rag.service.orchestration.agentic import (
    AgenticRAGOrchestrator,
    AgenticRAGRequest,
)
from rag.service.reranker.interface import RerankerProvider
from server.dependencies import (
    get_elasticsearch_client,
    get_embedding_provider,
    get_llm_provider,
    get_optional_reranker_provider,
)
from server.routes.agentic_ask.schema import AgenticAskRequest, AgenticAskResponse

router = APIRouter(tags=["agentic-rag"])


@router.post("/ask-agentic", response_model=AgenticAskResponse)
async def agentic_ask(
    request: AgenticAskRequest,
    elasticsearch_client: ElasticsearchClient = Depends(get_elasticsearch_client),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    reranker_provider: RerankerProvider | None = Depends(
        get_optional_reranker_provider
    ),
) -> AgenticAskResponse:
    settings = get_settings()

    if not settings.agentic_rag_settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agentic RAG is disabled.",
        )

    searching_service = SearchingService(
        elasticsearch_client=elasticsearch_client,
        embedding_provider=embedding_provider,
    )
    orchestrator = AgenticRAGOrchestrator(
        settings=settings.agentic_rag_settings,
        searching_service=searching_service,
        llm_provider=llm_provider,
        reranker_provider=reranker_provider,
    )

    try:
        result = await orchestrator.answer(
            AgenticRAGRequest(
                question=request.question,
                thread_id=request.thread_id,
                retrieval_mode=request.retrieval_mode,
                top_k=request.top_k,
                candidate_pool_size=request.candidate_pool_size,
                use_reranker=request.use_reranker,
                num_candidates=request.num_candidates,
                categories=request.categories,
                paper_id=(
                    str(request.paper_id) if request.paper_id is not None else None
                ),
                published_from=(
                    request.published_from.isoformat()
                    if request.published_from is not None
                    else None
                ),
                published_to=(
                    request.published_to.isoformat()
                    if request.published_to is not None
                    else None
                ),
                latest_first=request.latest_first,
                min_score=request.min_score,
                track_total_hits=request.track_total_hits,
                include_highlights=request.include_highlights,
                fuzziness=request.fuzziness,
            )
        )

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Agentic ask failed: {error}",
        ) from error

    return AgenticAskResponse.model_validate(result.to_dict())
