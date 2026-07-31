# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from rag.config import get_settings
from rag.db.config import Base

# REQUIRED IMPORT
from rag.db.model import PaperModel, ChunkModel # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

# set sql alchemy db url
config.set_main_option("sqlalchemy.url", settings.postgres_settings.db_url)

# metadata is the collection of SQLAlchemy tables from all models
# any class inherited from the `Base` itself
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    offline migrations generates .sql file to perform manual migration
    with no db connection
    """
    url = config.get_main_option("sqlalchemy.url")

    # enable literal_binds to render values directly into the SQL text
    # instead of using bound parameters
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    online migrations applies migration directly with db connection
    """
    # build SQL alchemy engine using alembic config
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
