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
                # custom pre-processing pipeline
                "analyzer": {
                    # original text
                    "main_text_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    },
                    # stemmed text
                    "stemmed_text_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "snowball"],
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
                    "analyzer": "main_text_analyzer",
                    "fields": {
                        "stemmed": {
                            "type": "text",
                            "analyzer": "stemmed_text_analyzer",
                        }
                    },
                },
                "chunk_word_count": {"type": "integer"},
                "section_title": {
                    "type": "text",
                    "analyzer": "main_text_analyzer",
                    "fields": {
                        "stemmed": {
                            "type": "text",
                            "analyzer": "stemmed_text_analyzer",
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
                    "analyzer": "main_text_analyzer",
                    "fields": {
                        "stemmed": {
                            "type": "text",
                            "analyzer": "stemmed_text_analyzer",
                        }
                    },
                },
                "authors": {
                    "type": "text",
                    "analyzer": "main_text_analyzer",
                },
                "abstract": {
                    "type": "text",
                    "analyzer": "main_text_analyzer",
                    "fields": {
                        "stemmed": {
                            "type": "text",
                            "analyzer": "stemmed_text_analyzer",
                        }
                    },
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
