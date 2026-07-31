# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.service.embedding.config.interface import EmbeddingProvider
from rag.service.embedding.config.factory import create_embedding

__all__ = ["EmbeddingProvider", "create_embedding"]
