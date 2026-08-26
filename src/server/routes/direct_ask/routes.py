# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from fastapi import APIRouter, Depends, HTTPException, status

from rag.service.embedding.config.embedding_interface import EmbeddingProvider
from rag.service.elasticsearch.config.es_client import ElasticsearchClient
from rag.service.elasticsearch.searching import SearchingService
from rag.service.llm.llm_interface import LLMProvider
from rag.service.orchestration.core.direct import (
    DirectRagNonRetryableError,
    DirectRagOrchestrator,
    DirectRagRequest,
    DirectRagRetryableError,
    DirectRagServiceError,
    DirectRagValidationError,
)
from rag.service.reranker.reranker_interface import RerankerProvider
from server.dependencies import (
    get_elasticsearch_client,
    get_embedding_provider,
    get_llm_provider,
    get_optional_reranker_provider,
)
from server.routes.direct_ask.schema import DirectAskRequest, DirectAskResponse

router = APIRouter(tags=["direct-rag"])


@router.post("/ask", response_model=DirectAskResponse)
async def direct_ask(
    request: DirectAskRequest,
    elasticsearch_client: ElasticsearchClient = Depends(get_elasticsearch_client),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    reranker_provider: RerankerProvider | None = Depends(
        get_optional_reranker_provider
    ),
) -> DirectAskResponse:
    if request.use_reranker and reranker_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reranker provider is not initialized.",
        )

    searching_service = SearchingService(
        elasticsearch_client=elasticsearch_client,
        embedding_provider=embedding_provider,
    )
    orchestrator = DirectRagOrchestrator(
        searching_service=searching_service,
        llm_provider=llm_provider,
        reranker_provider=reranker_provider,
    )

    try:
        direct_request = DirectRagRequest(
            question=request.question,
            retrieval_mode=request.retrieval_mode,
            top_k=request.top_k,
            candidate_pool_size=request.candidate_pool_size,
            use_reranker=request.use_reranker,
            num_candidates=request.num_candidates,
            categories=request.categories,
            paper_id=str(request.paper_id) if request.paper_id is not None else None,
            published_from=request.published_from,
            published_to=request.published_to,
            latest_first=request.latest_first,
            min_score=request.min_score,
            track_total_hits=request.track_total_hits,
            include_highlights=request.include_highlights,
            fuzziness=request.fuzziness,
        )
        result = await orchestrator.answer(direct_request)

    except DirectRagValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    except DirectRagNonRetryableError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    except DirectRagRetryableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    except DirectRagServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Direct ask failed: {error}",
        ) from error

    return DirectAskResponse.model_validate(result.to_dict())
