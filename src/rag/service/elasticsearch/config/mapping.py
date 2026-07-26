# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from typing import Any

CHUNK_INDEX_MAPPING_VERSION = 1


def create_chunk_index_mapping(vector_dimension: int) -> dict[str, Any]:
    return {
        # ELASTICSEARCH SETTINGS
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    # custom pre-processing pipeline
                    "preprocessing_pipeline": {
                        "type": "custom",
                        # NOTE: stemmer can hurt scientific papers. (need more research about this)
                        # lowercase + stopwords + snowball stemmer + tokenize
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "snowball"],
                    }
                }
            },
        },
        # ELASTICSEARCH DOCUMENT SCHEMA
        "mappings": {
            "_meta": {
                "mapping_version": CHUNK_INDEX_MAPPING_VERSION,
            },
            "dynamic": "strict",  # strict if field mismatch during insertion
            "properties": {
                "chunk_id": {"type": "keyword"},
                "paper_id": {"type": "keyword"},
                "arxiv_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "chunk_text": {
                    "type": "text",
                    "analyzer": "preprocessing_pipeline",
                },
                "chunk_word_count": {"type": "integer"},
                "section_title": {
                    "type": "text",
                    "analyzer": "preprocessing_pipeline",
                    "fields": {
                        "keyword": {
                            "type": "keyword", # extra keyword field
                            "ignore_above": 256, # ignore above 256 characters
                        }
                    },
                },
                "start_word": {"type": "integer"},
                "end_word": {"type": "integer"},
                "start_char": {"type": "integer"},
                "end_char": {"type": "integer"},
                "overlap_with_previous": {"type": "integer"},
                "overlap_with_next": {"type": "integer"},
                "source_storage_key": {"type": "keyword"},
                "title": {
                    "type": "text",
                    "analyzer": "preprocessing_pipeline",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256,
                        }
                    },
                },
                "authors": {
                    "type": "text",
                    "analyzer": "preprocessing_pipeline",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256,
                        }
                    },
                },
                "abstract": {
                    "type": "text",
                    "analyzer": "preprocessing_pipeline",
                },
                "categories": {"type": "keyword"},
                "published_date": {"type": "date"},
                "pdf_url": {"type": "keyword"},
                "pdf_storage_key": {"type": "keyword"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": vector_dimension,
                    "index": True,
                    "similarity": "cosine",
                },
                "embedding_model": {"type": "keyword"},
                "embedding_dimension": {"type": "integer"},
                "indexed_at": {"type": "date"},
            },
        },
    }
