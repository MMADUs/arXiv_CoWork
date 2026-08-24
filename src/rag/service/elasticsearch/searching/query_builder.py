# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from datetime import date
from typing import Any


class ElasticsearchQueryBuilder:
    """
    `ElasticsearchQueryBuilder` is responsible to construct the elasticsearch query

    since the query is pretty complicated, its best to make its own class

    Args:
        categories:
            search by selected list of categories
        paper_id:
            search documents by paper id
        published_from:
            filter search starting date of paper publish date
        published_to:
            filter latest date of paper publish date
        track_total_hits:
            whether Elasticsearch should compute the exact total number of matching documents
        min_score:
            any searched document score that is below the min_score threshold will be filtered out
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
        if (
            published_from is not None
            and published_to is not None
            and published_from > published_to
        ):
            raise ValueError("published_from must be before or equal to published_to")

        self.categories = categories
        self.paper_id = paper_id
        self.published_from = published_from
        self.published_to = published_to
        self.track_total_hits = track_total_hits
        self.min_score = min_score

        self._validate_filters()

    def bm25(
        self,
        query: str,
        size: int,
        offset: int,
        latest_first: bool = False,
        fuzziness: str | None = None,
        include_highlights: bool = True,
    ) -> dict[str, Any]:
        """
        Build BM25 search request body query

        Args:
            query:
                user input text query for search
            size:
                the size of returned matching documents (refer to top-K matching)
            offset:
                how many results to skip before returning results (useful for pagination query)
            latest_first:
                filter flag to makes returned document in latest first order by publish date,
                so score order still aplies afterwards when the date being the primary sort factor
            fuzziness:
                typo-tolerance setting for the multi_match query, such as "AUTO".
                Leave as None for normal BM25 matching (maybe make it literal ???)
            include_highlights:
                include similarity highlights inside searched documents
        """
        request_body = self._base_body(size=size, offset=offset)

        request_body["query"] = {
            "bool": {
                "must": (
                    [self._bm25_query(query, fuzziness=fuzziness)]
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

        if include_highlights:
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
        candidate_pool_size: int | None = None,
        num_candidates: int | None = None,
    ) -> dict[str, Any]:
        """
        Build vector/KNN search request body

        Args:
            query_vector:
                embedding vector for the search query
            size:
                the size of returned matching documents (useful for pagination query)
            offset:
                how many results to skip before returning results (useful for pagination query)
            candidate_pool_size:
                number of nearest vector matches to keep before pagination, defaults to
                size + offset (must be at least size + offset)
            num_candidates:
                number of candidate vectors elasticsearch should inspect during approximate
                KNN search, higher values can improve recall but make search slower
        """
        if not query_vector:
            raise ValueError("query_vector must not be empty")

        k = self._candidate_pool_size(
            size=size,
            offset=offset,
            candidate_pool_size=candidate_pool_size,
        )

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

    def _base_body(self, size: int, offset: int) -> dict[str, Any]:
        if size < 1:
            raise ValueError("size must be greater than 0")

        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        body: dict[str, Any] = {
            "from": offset,
            "size": size,
            "track_total_hits": self.track_total_hits,
            "_source": self._source_fields(),
        }

        if self.min_score is not None:
            body["min_score"] = self.min_score

        return body

    def _bm25_query(self, query: str, fuzziness: str | None) -> dict[str, Any]:
        multi_match: dict[str, Any] = {
            "query": query,
            "fields": [
                "title^4",
                "title.stemmed^2",
                "abstract^2",
                "abstract.stemmed",
                "section_title^1.5",
                "section_title.stemmed",
                "chunk_text",
                "chunk_text.stemmed",
            ],
            "type": "best_fields",
            "operator": "or",
        }

        if fuzziness is not None:
            multi_match["fuzziness"] = fuzziness

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

        if self.published_to is not None:
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
        """
        highlight matching keyword from searched document
        """
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

    def _candidate_pool_size(
        self,
        size: int,
        offset: int,
        candidate_pool_size: int | None,
    ) -> int:
        minimum = size + offset

        if candidate_pool_size is None:
            return minimum

        if candidate_pool_size < minimum:
            raise ValueError(
                "candidate_pool_size must be greater than or equal to size + offset"
            )

        return candidate_pool_size
