# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from rag.service.elasticsearch.config.client import ElasticsearchClient
from rag.service.storage import StorageProvider
from server.dependencies import (
    get_db_session,
    get_elasticsearch_client,
    get_s3_storage,
)
from server.routes.removal.removal_helpers import (
    PaperRemovalConflictError,
    PaperRemovalNotFoundError,
    delete_paper_index,
    delete_paper_metadata,
)
from server.routes.removal.removal_schema import (
    DeletePaperIndexResponse,
    DeletePaperMetadataResponse,
)

router = APIRouter(prefix="/papers", tags=["paper-removal"])


@router.delete(
    "/metadata/{paper_id}",
    response_model=DeletePaperMetadataResponse,
    status_code=status.HTTP_200_OK,
)
def delete_paper_metadata_route(
    paper_id: UUID,
    session: Session = Depends(get_db_session),
    storage: StorageProvider = Depends(get_s3_storage),
) -> DeletePaperMetadataResponse:
    try:
        return delete_paper_metadata(
            paper_id=paper_id,
            session=session,
            storage=storage,
        )

    except PaperRemovalNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except PaperRemovalConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to delete paper metadata: {error}",
        ) from error


@router.delete(
    "/index/{paper_id}",
    response_model=DeletePaperIndexResponse,
    status_code=status.HTTP_200_OK,
)
def delete_paper_index_route(
    paper_id: UUID,
    session: Session = Depends(get_db_session),
    elasticsearch_client: ElasticsearchClient = Depends(get_elasticsearch_client),
) -> DeletePaperIndexResponse:
    try:
        return delete_paper_index(
            paper_id=paper_id,
            session=session,
            elasticsearch_client=elasticsearch_client,
        )

    except PaperRemovalNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except PaperRemovalConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to delete paper index: {error}",
        ) from error
