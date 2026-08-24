# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from typing import Any, TypeAlias

from elasticsearch import Elasticsearch, BadRequestError, NotFoundError, helpers

from rag.config import ElasticsearchSettings
from rag.service.elasticsearch.config.es_index_mapping import create_chunk_index_mapping
from rag.service.elasticsearch.es_exceptions import (
    ElasticsearchBulkIndexError,
    ElasticsearchDeleteError,
    ElasticsearchIndexError,
    ElasticsearchResponseError,
    ElasticsearchSearchError,
    ElasticsearchServiceError,
)

# TODO: since searching is the core system of retrieval, here are future improvement to implement:
#       1. expose elasticsearch index stats through API (to make system more centralized)
#       2. make better query for specific search, eg: retrieved chunks by paper
#       3. more things coming, we'll see

# elasticsearch raw json response type alias
# because elasticsearch returns a messy json response
ESRawJsonResponse: TypeAlias = dict[str, Any]


@dataclass(slots=True)
class EnsureIndexResult:
    """
    Response schema for ensuring elasticsearch index existence
    """

    index_name: str
    created: bool
    exists: bool
    response: ESRawJsonResponse


@dataclass(slots=True)
class DeleteIndexResult:
    """
    Response schema for elasticsearch index deletion
    """

    index_name: str
    acknowledged: bool
    deleted: bool
    response: ESRawJsonResponse


@dataclass(slots=True)
class InsertedBulkItem:
    """
    Since bulk/stream insertion has potential partial success,
    each inserted item needs a clear insertion status and error
    """

    id: str
    ok: bool
    status: int
    error: str | None


@dataclass(slots=True)
class BulkIndexResult:
    """
    Bulk or stream insertion to index response schema
    """

    errors: bool
    indexed_count: int
    items: list[InsertedBulkItem]


@dataclass(slots=True)
class DeleteChunksByPaperResult:
    """
    Delete chunks by paper response schema
    """

    exists: bool
    deleted: int
    version_conflicts: int = 0
    failures: list[Any] | None = None


@dataclass(slots=True)
class SearchHit:
    """
    Elasticsearch search hit item result, holds the document source with highlight
    """

    id: str
    score: float | None
    source: dict[str, Any]
    highlights: list[str]

    @property
    def chunk_id(self) -> str:
        return str(self.source.get("chunk_id", self.id))

    @property
    def chunk_text(self) -> str:
        return str(self.source.get("chunk_text", ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "elasticsearch_document_id": self.id,
            "score": self.score,
            "highlights": self.highlights,
            **self.source,
        }

    @classmethod
    def from_elasticsearch_hit(cls, hit: dict[str, Any]) -> "SearchHit":
        # highlights holds many snippets (the highlighted text)
        highlights: list[str] = []

        for snippets in hit.get("highlight", {}).values():
            highlights.extend(str(snippet) for snippet in snippets)

        return cls(
            id=str(hit["_id"]),
            score=hit.get("_score"),
            source=dict(hit.get("_source", {})),
            highlights=highlights,
        )


@dataclass(slots=True)
class SearchResult:
    """
    Elasticsearch document search result schema
    """

    total: int
    hits: list[SearchHit]
    raw_response: ESRawJsonResponse

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "items": [hit.to_dict() for hit in self.hits],
        }

    @classmethod
    def from_elasticsearch_response(
        cls,
        response: ESRawJsonResponse,
    ) -> "SearchResult":
        hits_data = response["hits"]
        total_data = hits_data["total"]

        # TODO: why is this very vague about response payload ?
        if isinstance(total_data, dict):
            total = int(total_data["value"])
        else:
            total = int(total_data)

        return cls(
            total=total,
            hits=[
                SearchHit.from_elasticsearch_hit(hit)
                for hit in hits_data.get("hits", [])
            ],
            raw_response=response,
        )


class ElasticsearchClient:
    def __init__(self, settings: ElasticsearchSettings) -> None:
        self.base_url = settings.base_url
        self.chunk_index_name = settings.chunk_index_name
        self.vector_dimension = settings.vector_dimension
        self.timeout_seconds = settings.timeout_seconds

        client_kwargs: dict[str, Any] = {
            "request_timeout": settings.timeout_seconds,
            "retry_on_timeout": True,
            "verify_certs": settings.verify_certs,
            "ssl_show_warn": settings.ssl_show_warn,
        }

        # NOTE: choose only 1 out of the 3 auth strategy

        if settings.username and settings.password:
            client_kwargs["basic_auth"] = (settings.username, settings.password)

        if settings.api_key:
            client_kwargs["api_key"] = settings.api_key

        if settings.ca_certs:
            client_kwargs["ca_certs"] = settings.ca_certs

        self.client = Elasticsearch([self.base_url], **client_kwargs)

    def health_check(self) -> ESRawJsonResponse:
        try:
            return dict(self.client.cluster.health())

        except Exception as error:
            raise ElasticsearchSearchError(
                "Failed to fetch Elasticsearch cluster health"
            ) from error

    def chunk_index_exists(self) -> bool:
        """
        Check if index already exist

        Raises:
            ElasticsearchIndexError:
                when failed to check index existence
        """
        try:
            return bool(self.client.indices.exists(index=self.chunk_index_name))

        except Exception as error:
            raise ElasticsearchIndexError(
                f"Failed to check chunk index existence: {self.chunk_index_name}"
            ) from error

    def create_chunk_index(self) -> ESRawJsonResponse:
        """
        Create elasticsearch index for chunks

        Raises:
            ElasticsearchIndexError:
                when indexing failed to create
        """
        try:
            response = self.client.indices.create(
                index=self.chunk_index_name,
                body=create_chunk_index_mapping(self.vector_dimension),
            )

        except BadRequestError as error:
            if getattr(error, "error", None) == "resource_already_exists_exception":
                return {
                    "acknowledged": True,
                    "already_exists": True,
                }

            raise ElasticsearchIndexError(
                f"Failed to create chunk index: {self.chunk_index_name}"
            ) from error

        except ElasticsearchServiceError:
            raise

        except Exception as error:
            raise ElasticsearchIndexError(
                f"Failed to create chunk index: {self.chunk_index_name}"
            ) from error

        return dict(response)

    def delete_chunk_index(self) -> DeleteIndexResult:
        """
        Delete elasticsearch chunk index

        Raises:
            ElasticsearchDeleteError:
                if deleting index failed
        """
        try:
            response = self.client.indices.delete(index=self.chunk_index_name)

        except NotFoundError:
            return DeleteIndexResult(
                index_name=self.chunk_index_name,
                acknowledged=True,
                deleted=False,
                response={"acknowledged": True, "deleted": False},
            )

        except Exception as error:
            raise ElasticsearchDeleteError(
                f"Failed to delete chunk index: {self.chunk_index_name}"
            ) from error

        data = dict(response)

        return DeleteIndexResult(
            index_name=self.chunk_index_name,
            acknowledged=bool(data.get("acknowledged", False)),
            deleted=True,
            response=data,
        )

    def ensure_chunk_index(self, force: bool = False) -> EnsureIndexResult:
        """
        Make sure chunk index exist in elasticsearch

        Args:
            force:
                reset flag, meaning it force to delete and re-create new index

        Raises:
            ElasticsearchIndexError:
                when indexing failed to check or create
            ElasticsearchDeleteError:
                if deleting index failed when force is enabled
        """
        try:
            if force:
                self.delete_chunk_index()

            if self.chunk_index_exists():
                return EnsureIndexResult(
                    index_name=self.chunk_index_name,
                    created=False,
                    exists=True,
                    response={"acknowledged": True, "already_exists": True},
                )

            create_response: ESRawJsonResponse = self.create_chunk_index()
            created = not create_response.get("already_exists", False)

            return EnsureIndexResult(
                index_name=self.chunk_index_name,
                created=created,
                exists=True,
                response=create_response,
            )

        except ElasticsearchServiceError:
            raise

        except Exception as error:
            raise ElasticsearchIndexError(
                f"Failed to ensure chunk index: {self.chunk_index_name}"
            ) from error

    def bulk_index_chunks(self, documents: list[dict[str, Any]]) -> BulkIndexResult:
        """
        perform bulk indexing to elasticsearch

        documents args must have matched the returned properties of
        `create_chunk_index_mapping()` function

        Args:
            documents:
                list of json documents that contains payload with the mappings

        Raises:
            ElasticsearchBulkIndexError: if elasticsearch stream/bulk insertion fails
        """
        if not documents:
            return BulkIndexResult(errors=False, indexed_count=0, items=[])

        # build query actions for each document
        actions = [
            {
                "_op_type": "index",
                "_index": self.chunk_index_name,
                "_id": doc["chunk_id"],
                "_source": doc,
            }
            for doc in documents
        ]

        items: list[InsertedBulkItem] = []
        indexed_count = 0

        # bulk insertion operation
        try:
            for ok, item in helpers.streaming_bulk(
                client=self.client,
                actions=actions,
                refresh=True,
                raise_on_error=False,
                yield_ok=True,
            ):
                result = item.get("index", {})
                status = int(result.get("status", 0))

                if ok:
                    indexed_count += 1

                items.append(
                    InsertedBulkItem(
                        id=str(result.get("_id")),
                        ok=ok,
                        status=int(status),
                        error=str(result["error"]) if "error" in result else None,
                    )
                )

        except Exception as error:
            raise ElasticsearchBulkIndexError(
                "Failed to bulk index chunks into Elasticsearch"
            ) from error

        has_item_errors = any(not item.ok for item in items)

        return BulkIndexResult(
            errors=has_item_errors or indexed_count != len(documents),
            indexed_count=indexed_count,
            items=items,
        )

    def delete_chunks_by_paper(self, paper_id: str) -> DeleteChunksByPaperResult:
        """
        Delete document chunk by paper id

        Raises:
            ElasticsearchDeleteError:
                if deleting document index failed
        """
        try:
            if not self.chunk_index_exists():
                return DeleteChunksByPaperResult(
                    exists=False,
                    deleted=0,
                    failures=[],
                )

            data = self.client.delete_by_query(
                index=self.chunk_index_name,
                conflicts="proceed",
                refresh=True,
                body={
                    "query": {
                        "term": {
                            "paper_id": paper_id,
                        }
                    }
                },
            )

        except ElasticsearchServiceError:
            raise

        except Exception as error:
            raise ElasticsearchDeleteError(
                f"Failed to delete indexed chunks for paper: {paper_id}"
            ) from error

        return DeleteChunksByPaperResult(
            exists=True,
            deleted=int(data.get("deleted", 0)),
            version_conflicts=int(data.get("version_conflicts", 0)),
            failures=list(data.get("failures", [])),
        )

    def search(self, body: dict[str, Any]) -> SearchResult:
        """
        The main search interface in elasticsearch client class

        Args:
            body:
                since elasticsearch received request in http form, body is in json format, hence its a raw dict

        Raises:
            ElasticsearchResponseError:
                if elasticsearch response is invalid or missed the response payload expectation
            ElasticsearchSearchError:
                if the function catches any exception from client search (broad error here)
        """
        try:
            response = dict(
                self.client.search(
                    index=self.chunk_index_name,
                    body=body,
                )
            )
            return SearchResult.from_elasticsearch_response(response)

        except (KeyError, TypeError, ValueError) as error:
            raise ElasticsearchResponseError(
                "Elasticsearch search response is invalid"
            ) from error

        except Exception as error:
            raise ElasticsearchSearchError("Elasticsearch search failed") from error

    def close(self) -> None:
        self.client.close()
