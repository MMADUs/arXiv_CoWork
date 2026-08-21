# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from celery import Celery
from kombu import Queue

from rag.config import get_settings

settings = get_settings()
celery_settings = settings.celery_settings


def name_module(filename: str):
    """ 
    The string format must match exactly the same as the dir path

    Since all task are declared in /worker/tasks, therefore filename must match as well
    """
    return f"worker.tasks.{filename}"


def name_route(module_name: str):
    return f"{module_name}_route"


PDF_DOWNLOAD_MODULE = name_module("pdf_download_task")
PDF_DOWNLOAD_ROUTE = name_route(PDF_DOWNLOAD_MODULE)

PARSING_MODULE = name_module("paper_parsing_task")
PARSING_ROUTE = name_route(PARSING_MODULE)

CHUNKING_MODULE = name_module("paper_chunking_task")
CHUNKING_ROUTE = name_route(CHUNKING_MODULE)

INDEXING_MODULE = name_module("paper_indexing_task")
INDEXING_ROUTE = name_route(INDEXING_MODULE)

celery_app = Celery(
    "arxiv_cowork_worker",
    broker=celery_settings.broker_url,
    backend=celery_settings.result_backend,
    include=[
        PDF_DOWNLOAD_MODULE,
        PARSING_MODULE,
        CHUNKING_MODULE,
        INDEXING_MODULE,
    ],
)

celery_app.conf.update(
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_queues=(
        Queue(celery_settings.pdf_download_queue),
        Queue(celery_settings.parsing_queue),
        Queue(celery_settings.chunking_queue),
        Queue(celery_settings.indexing_queue),
    ),
    task_reject_on_worker_lost=True,
    task_routes={
        PDF_DOWNLOAD_ROUTE: {"queue": celery_settings.pdf_download_queue},
        PARSING_ROUTE: {"queue": celery_settings.parsing_queue},
        CHUNKING_ROUTE: {"queue": celery_settings.chunking_queue},
        INDEXING_ROUTE: {"queue": celery_settings.indexing_queue},
    },
    task_serializer="json",
    task_track_started=True,
    timezone="UTC",
    # NOTE: available for tuning, value can be vary to match needs
    worker_prefetch_multiplier=1,
)
