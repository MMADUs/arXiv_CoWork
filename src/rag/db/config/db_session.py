# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from rag.config import Settings, get_settings
from rag.db.config.db_interface import DatabaseProvider
from rag.db.config.db_factory import create_database

_global_db_session: DatabaseProvider | None = None


@contextmanager
def use_db_session(
    settings: Settings | None = None,
) -> Generator[Session, None, None]:
    """
    session helper for scripts that requires one time session
    """
    global _global_db_session

    if _global_db_session is None:
        _global_db_session = create_database(settings or get_settings())
        _global_db_session.startup()

    with _global_db_session.get_session() as session:
        yield session
