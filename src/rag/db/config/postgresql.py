# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, Session

from rag.db.config.db_interface import DatabaseProvider
from rag.config import PostgresSettings

logger = logging.getLogger(__name__)


class PostgreSQLDatabase(DatabaseProvider):
    """
    PostgreSQL db provider implementation
    """

    def __init__(self, settings: PostgresSettings):
        self.settings = settings
        self.engine: Engine | None = None
        self.session_factory: sessionmaker[Session] | None = None

    def startup(self) -> None:
        if self.engine is not None and self.session_factory is not None:
            return

        self.engine = create_engine(
            url=self.settings.db_url,
            echo=self.settings.echo_sql,
            pool_size=self.settings.pool_size,
            max_overflow=self.settings.max_overflow,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )

        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

        ok, message = self.check_connection()

        if not ok:
            self.shutdown()
            raise RuntimeError(f"PostgreSQL startup failed: {message}")

        logger.info("PostgreSQL database initialized")

    def check_connection(self) -> tuple[bool, str]:
        if self.engine is None:
            return False, "PostgreSQL is not initialized"

        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))

            return True, "PostgreSQL connected"

        except SQLAlchemyError as error:
            return False, str(error)

    def shutdown(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            logger.info("PostgreSQL database connections disposed")

        self.engine = None
        self.session_factory = None

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        if self.session_factory is None:
            raise RuntimeError("PostgreSQL is not initialized")

        session = self.session_factory()

        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
