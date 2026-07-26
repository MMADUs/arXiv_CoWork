# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import date
from typing import Any


class ElasticsearchQueryBuilder:
    """ 
    `ElasticsearchQueryBuilder` is responsible to construct the elasticsearch query

    since the query is pretty complicated, its best to make its own class
    """
    def __init__(
        self,
        categories: list[str] | None = None,
        paper_id: str | None = None,
        published_from: date | None = None,
        published_to: date | None = None,
        track_total_hits: bool = True,
        min_score: float | None = None,
    ) -> None:
        self.categories = categories
        self.paper_id = paper_id
        self.published_from = published_from
        self.published_to = published_to
        self.track_total_hits = track_total_hits
        self.min_score = min_score

    def bm25(
        self,
        query: str,
        size: int,
        offset: int,
        latest_first: bool = False,
    ) -> dict[str, Any]:
        request_body = self._base_body(size=size, offset=offset)

        request_body["query"] = {
            "bool": {
                "must": (
                    [self._bm25_query(query)]
                    if query.strip()
                    else [
                        {
                            "match_all": {},
                        }
                    ]
                ),
                "filter": self._filters(),
            }
        }
        request_body["highlight"] = self._highlight_config()

        if latest_first:
            request_body["sort"] = [
                {
                    "published_date": {
                        "order": "desc",
                    }
                },
                "_score",
            ]

        return request_body

    def vector(
        self,
        query_vector: list[float],
        size: int,
        offset: int,
        num_candidates: int | None = None,
    ) -> dict[str, Any]:
        k = size + offset

        request_body = self._base_body(size=size, offset=offset)

        request_body["knn"] = {
            "field": "embedding",
            "query_vector": query_vector,
            "k": k,
            "num_candidates": num_candidates or max(100, k),
        }

        filters = self._filters()

        if filters:
            request_body["knn"]["filter"] = {
                "bool": {
                    "filter": filters,
                }
            }

        return request_body

    def hybrid_rrf(
        self,
        query: str,
        query_vector: list[float],
        size: int,
        offset: int,
        rank_window_size: int,
        rank_constant: int = 60,
        num_candidates: int | None = None,
    ) -> dict[str, Any]:
        k = rank_window_size

        request_body = self._base_body(size=size, offset=offset)

        request_body["retriever"] = {
            "rrf": {
                "retrievers": [
                    {
                        "standard": {
                            "query": {
                                "bool": {
                                    "must": (
                                        [self._bm25_query(query)]
                                        if query.strip()
                                        else [{"match_all": {}}]
                                    )
                                }
                            }
                        }
                    },
                    {
                        "knn": {
                            "field": "embedding",
                            "query_vector": query_vector,
                            "k": k,
                            "num_candidates": num_candidates or max(100, k),
                        }
                    },
                ],
                "rank_window_size": rank_window_size,
                "rank_constant": rank_constant,
            }
        }
        request_body["highlisht"] = self._highlight_config()

        filters = self._filters()

        if filters:
            request_body["retriever"]["rrf"]["filter"] = filters

        return request_body

    def _base_body(self, size: int, offset: int) -> dict[str, Any]:
        body: dict[str, Any] = {
            "from": offset,
            "size": size,
            "track_total_hits": self.track_total_hits,
            "_source": self._source_fields(),
        }

        if self.min_score is not None:
            body["min_score"] = self.min_score

        return body

    def _bm25_query(self, query: str) -> dict[str, Any]:
        multi_match: dict[str, Any] = {
            "query": query,
            "fields": [
                "title^4",
                "abstract^2",
                "section_title^1.5",
                "chunk_text",
            ],
            "type": "best_fields",
            "operator": "or",
        }

        if not self._is_short_technical_query(query):
            multi_match["fuzziness"] = "AUTO"
            multi_match["prefix_length"] = 2

        return {
            "multi_match": multi_match,
        }

    def _filters(self) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []

        if self.categories:
            filters.append(
                {
                    "terms": {
                        "categories": self.categories,
                    }
                }
            )

        if self.paper_id:
            filters.append(
                {
                    "term": {
                        "paper_id": self.paper_id,
                    }
                }
            )

        date_range: dict[str, str] = {}

        if self.published_from is not None:
            date_range["gte"] = self.published_from.isoformat()

        if self.published_from is not None:
            date_range["lte"] = self.published_to.isoformat()

        if date_range:
            filters.append(
                {
                    "range": {
                        "published_date": date_range,
                    }
                }
            )

        return filters

    def _highlight_config(self) -> dict[str, Any]:
        return {
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
            "require_field_match": False,
            "fields": {
                "chunk_text": {
                    "fragment_size": 180,
                    "number_of_fragments": 3,
                },
                "title": {
                    "number_of_fragments": 0,
                },
                "abstract": {
                    "fragment_size": 180,
                    "number_of_fragments": 2,
                },
                "section_title": {
                    "number_of_fragments": 0,
                },
            },
        }

    def _source_fields(self) -> list[str]:
        return [
            "chunk_id",
            "paper_id",
            "arxiv_id",
            "chunk_index",
            "chunk_text",
            "chunk_word_count",
            "section_title",
            "start_word",
            "end_word",
            "start_char",
            "end_char",
            "overlap_with_previous",
            "overlap_with_next",
            "source_storage_key",
            "title",
            "authors",
            "abstract",
            "categories",
            "published_date",
            "pdf_url",
            "pdf_storage_key",
            "embedding_model",
            "embedding_dimension",
            "indexed_at",
        ]

    def _is_short_technical_query(self, query: str) -> bool:
        normalized = query.strip().upper()
        return normalized in {"AI", "ML", "NN", "CV", "NLP", "RAG", "LLM"}
