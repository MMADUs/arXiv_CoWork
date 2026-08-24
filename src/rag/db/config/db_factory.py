# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from rag.config import Settings, get_settings
from rag.db.config.db_interface import DatabaseProvider
from rag.db.config.postgresql import PostgreSQLDatabase


def create_database(settings: Settings | None = None) -> DatabaseProvider:
    settings = settings or get_settings()

    return PostgreSQLDatabase(settings.postgres_settings)
