"""Alembic environment: resolves the target database from ``DATABASE_URL``."""

from __future__ import annotations

import logging
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings  # noqa: F401  (loads the project .env first)

config = context.config

# Deliberately NOT calling fileConfig(config.config_file_name) here: the
# stock alembic.ini [loggers] section would reset the process-wide root
# logger (level + handlers), clobbering the application's structured-logging
# setup at startup. Alembic's own records flow through the app's root logger.
logging.getLogger("alembic").setLevel(logging.INFO)


def _url() -> str:
    return os.environ.get("DATABASE_URL") or settings.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
