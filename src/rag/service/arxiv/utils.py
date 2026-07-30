# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


def make_arxiv_id_safe(arxiv_id: str) -> str:
    """
    replace / to _ to prevent directory path mismatch when storing file with arxiv id
    """
    return arxiv_id.replace("/", "_")
