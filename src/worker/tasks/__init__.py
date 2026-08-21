# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from worker.tasks.paper_chunking_task import paper_chunker_task_route
from worker.tasks.paper_indexing_task import paper_indexing_task_route
from worker.tasks.paper_parsing_task import paper_parser_task_route

__all__ = [
    "paper_chunker_task_route",
    "paper_indexing_task_route",
    "paper_parser_task_route",
]
