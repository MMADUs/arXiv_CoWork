# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.

    Models that inherit from this class are registered in `Base.metadata`,
    which Alembic uses to detect schema changes during migration generation.
    """
    pass
