import os
import ssl
import asyncio
from logging.config import fileConfig
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

from app.database import Base
from app.models import (  # noqa: F401 – ensure all models are imported
    User, Mission, SousMission, Declaration, LigneDeclaration
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No DATABASE_URL env var and no sqlalchemy.url in alembic.ini")
    return url.strip().strip("'").strip('"')


def _to_asyncpg_sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _sanitize_asyncpg_url(url: str) -> str:
    """
    asyncpg.connect() does NOT accept libpq-style params like sslmode/channel_binding.
    If present in the querystring, SQLAlchemy's asyncpg dialect will pass them through
    as kwargs -> TypeError. We remove them and enforce TLS via connect_args.
    """
    parts = urlsplit(url)
    q = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
         if k.lower() not in {"sslmode", "channel_binding"}]
    new_query = urlencode(q, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def run_migrations_offline() -> None:
    url = _sanitize_asyncpg_url(_to_asyncpg_sqlalchemy_url(_get_database_url()))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = _sanitize_asyncpg_url(_to_asyncpg_sqlalchemy_url(_get_database_url()))

    ssl_ctx = ssl.create_default_context()

    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={"ssl": ssl_ctx},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()