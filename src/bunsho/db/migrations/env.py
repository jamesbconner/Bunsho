"""Alembic environment: online migrations of ``progress.db`` through stdlib sqlite."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL, make_url

from bunsho.db.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Migrate the database named by ``config.attributes['db_path']`` (or ``alembic.ini``)."""
    db_path = config.attributes.get("db_path")
    if db_path is not None:
        url = URL.create("sqlite", database=str(db_path))
    else:
        configured = config.get_main_option("sqlalchemy.url")
        if configured is None:
            raise RuntimeError("set Config.attributes['db_path'] or sqlalchemy.url in alembic.ini")
        url = make_url(configured)
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported for progress.db")
run_migrations_online()
