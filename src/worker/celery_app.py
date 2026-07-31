# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from celery import Celery
from kombu import Queue

from rag.config import get_settings

settings = get_settings()
celery_settings = settings.celery_settings

celery_app = Celery(
    "arxiv_cowork_worker",
    broker=celery_settings.broker_url,
    backend=celery_settings.result_backend,
    include=[
        "worker.tasks.parser_task",
        "worker.tasks.chunker_task",
        "worker.tasks.indexing_task",
    ],
)

celery_app.conf.update(
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_default_queue=celery_settings.default_queue,
    task_queues=(
        Queue(celery_settings.parsing_queue),
        Queue(celery_settings.chunking_queue),
        Queue(celery_settings.indexing_queue),
    ),
    task_reject_on_worker_lost=True,
    task_routes={
        "worker.tasks.parse_paper": {"queue": celery_settings.parsing_queue},
        "worker.tasks.chunk_paper": {"queue": celery_settings.chunking_queue},
        "worker.tasks.index_paper_chunks": {"queue": celery_settings.indexing_queue},
    },
    task_serializer="json",
    task_track_started=True,
    timezone="UTC",
    worker_prefetch_multiplier=1,
)
