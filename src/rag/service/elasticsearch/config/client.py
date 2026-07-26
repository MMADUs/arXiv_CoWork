# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from typing import Any, TypeAlias

from elasticsearch import Elasticsearch, BadRequestError, NotFoundError, helpers

from rag.config import ElasticsearchSettings
from rag.service.elasticsearch.config.mapping import create_chunk_index_mapping

# elasticsearch raw json response type alias
# because elasticsearch returns a messy json response smh
ESRawJsonResponse: TypeAlias = dict[str, Any]


@dataclass(slots=True)
class EnsureIndexResult:
    index_name: str
    created: bool
    exists: bool
    response: ESRawJsonResponse


@dataclass(slots=True)
class InsertedBulkItem:
    id: str
    ok: bool
    status: int
    error: str


@dataclass(slots=True)
class BulkIndexResult:
    errors: bool
    indexed_count: int
    items: list[InsertedBulkItem]


# @dataclass(slots=True)
# class DeleteChunkResult:

# NOTE: still need to work on this class, because ES response is messy


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
            "ssl_show_warn": True,
        }

        if settings.username and settings.password:
            client_kwargs["basic_auth"] = (settings.username, settings.password)

        if settings.api_key:
            client_kwargs["api_key"] = settings.api_key

        if settings.ca_certs:
            client_kwargs["ca_certs"] = settings.ca_certs

        self.client = Elasticsearch([self.base_url], **client_kwargs)

    def health_check(self) -> ESRawJsonResponse:
        return dict(self.client.cluster.health())

    def chunk_index_exists(self) -> bool:
        return bool(self.client.indices.exists(index=self.chunk_index_name))

    def create_chunk_index(self) -> ESRawJsonResponse:
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

            raise

        return dict(response)

    def delete_chunk_index(self) -> ESRawJsonResponse:
        try:
            response = self.client.indices.delete(index=self.chunk_index_name)

        except NotFoundError:
            return {
                "acknowledged": True,
                "deleted": False,
            }

        data = dict(response)
        data["deleted"] = True
        return data

    def ensure_chunk_index(self, force: bool = False) -> dict[str, Any]:
        if force:
            self.delete_chunk_index()

        if self.chunk_index_exists():
            # metadata_response = self.update_chunk_index_mapping_metadata()

            return {
                "index_name": self.chunk_index_name,
                "created": False,
                "exists": True,
                # "mapping_metadata_updated": metadata_response.get("acknowledge", False),
            }

        create_response: ESRawJsonResponse = self.create_chunk_index()
        created = not create_response.get("already_exists", False)

        return EnsureIndexResult(
            index_name=self.chunk_index_name,
            created=created,
            exists=True,
            response=create_response,
        )

    # def update_chunk_index_mapping_metadata(self) -> dict[str, Any]:
    #     response = self.client.indices.put_mapping(
    #         index=self.chunk_index_name,
    #         body={
    #             "_meta": {
    #                 "mapping_version": CHUNK_INDEX_MAPPING_VERSION,
    #             },
    #             "properties": {
    #                 "start_char": {"type": "integer"},
    #                 "end_char": {"type": "integer"},
    #                 "overlap_with_previous": {"type": "integer"},
    #                 "overlap_with_next": {"type": "integer"},
    #             },
    #         },
    #     )

    #     return dict(response)

    # def get_chunk_index_stats(self) -> dict[str, Any]:
    #     if not self.chunk_index_exists():
    #         return {
    #             "index_name": self.chunk_index_name,
    #             "exists": False,
    #             "document_count": 0,
    #             "size_in_bytes": 0,
    #             "unique_papers": 0,
    #             "average_chunks_per_paper": 0.0,
    #             "last_indexed_at": None,
    #             "mapping_version": None,
    #             "expected_mapping_version": CHUNK_INDEX_MAPPING_VERSION,
    #         }

    #     count_response = self.client.count(index=self.chunk_index_name)
    #     stats_response = self.client.indices.stats(
    #         index=self.chunk_index_name,
    #         metric="store",
    #     )
    #     search_response = self.client.search(
    #         index=self.chunk_index_name,
    #         body={
    #             "size": 0,
    #             "aggs": {
    #                 "unique_papers": {
    #                     "cardinality": {
    #                         "field": "paper_id",
    #                     }
    #                 },
    #                 "last_indexed_at": {
    #                     "max": {
    #                         "field": "indexed_at",
    #                     }
    #                 },
    #             },
    #         },
    #     )
    #     mapping_response = self.client.indices.get_mapping(
    #         index=self.chunk_index_name,
    #     )

    #     index_stats = stats_response["indices"][self.chunk_index_name]["total"]
    #     document_count = int(count_response["count"])
    #     aggregations = search_response["aggregations"]
    #     unique_papers = aggregations["unique_papers"]["value"]
    #     last_indexed_at = aggregations["last_indexed_at"].get("value_as_string")
    #     average_chunks_per_paper = (
    #         round(document_count / unique_papers, 2) if unique_papers else 0.0
    #     )
    #     mappings = mapping_response[self.chunk_index_name]["mappings"]
    #     mapping_version = mappings.get("_meta", {}).get("mapping_version")

    #     return {
    #         "index_name": self.chunk_index_name,
    #         "exists": True,
    #         "document_count": document_count,
    #         "size_in_bytes": index_stats["store"]["size_in_bytes"],
    #         "unique_papers": unique_papers,
    #         "average_chunks_per_paper": average_chunks_per_paper,
    #         "last_indexed_at": last_indexed_at,
    #         "mapping_version": mapping_version,
    #         "expected_mapping_version": CHUNK_INDEX_MAPPING_VERSION,
    #     }

    def bulk_index_chunks(self, documents: list[dict[str, Any]]) -> BulkIndexResult:
        """
        perform bulk indexing to elasticsearch

        documents args must have matched the returned properties of `create_chunk_index_mapping()` function
        """
        if not documents:
            return BulkIndexResult(errors=False, indexed_count=0, items=[])

        # query actions
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

        # bulk operations
        # NOTE: verify some of the variables again
        for ok, item in helpers.streaming_bulk(
            client=self.client,
            actions=actions,
            refresh=True,  # this exist or no ?
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
                    status=int(status),  # wtf is this ??
                    error=str(result.get("error")),
                )
            )

        return BulkIndexResult(
            errors=indexed_count != len(documents),
            indexed_count=indexed_count,
            items=items,
        )

    def delete_chunks_by_paper(self, paper_id: str) -> dict[str, Any]:
        if not self.chunk_index_exists():
            return {
                "index_name": self.chunk_index_name,
                "exists": False,
                "deleted": 0,
            }

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

        return {
            "index_name": self.chunk_index_name,
            "exists": True,
            "deleted": data.get("deleted", 0),
            "version_conflicts": data.get("version_conflicts", 0),
            "failures": data.get("failures", []),
        }

    # def get_chunks_by_paper(
    #     self,
    #     paper_id: str | None = None,
    #     arxiv_id: str | None = None,
    #     size: int = 1000,
    # ) -> list[dict[str, Any]]:
    #     if paper_id is None and arxiv_id is None:
    #         raise ValueError("paper_id or arxiv_id is required")

    #     if not self.chunk_index_exists():
    #         return []

    #     filters = []

    #     if paper_id is not None:
    #         filters.append({"term": {"paper_id": paper_id}})

    #     if arxiv_id is not None:
    #         filters.append({"term": {"arxiv_id": arxiv_id}})

    #     response = self.client.search(
    #         index=self.chunk_index_name,
    #         body={
    #             "size": size,
    #             "query": {
    #                 "bool": {
    #                     "filter": filters,
    #                 }
    #             },
    #             "sort": [
    #                 {"chunk_index": {"order": "asc"}},
    #             ],
    #             "_source": {
    #                 "excludes": ["embedding"],
    #             },
    #         },
    #     )

    #     chunks = []

    #     for hit in response["hits"]["hits"]:
    #         chunk = dict(hit["_source"])
    #         chunk["elasticsearch_document_id"] = hit["_id"]
    #         chunks.append(chunk)

    #     return chunks

    def search(self, body: dict[str, Any]) -> dict[str, Any]:
        return dict(
            self.client.search(
                index=self.chunk_index_name,
                body=body,
            )
        )

    def close(self) -> None:
        self.client.close()
