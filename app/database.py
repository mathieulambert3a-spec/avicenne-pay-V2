from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import os
import ssl
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy import event
from sqlalchemy.engine import Engine

# Import de la configuration
try:
    from app.config import DATABASE_URL
except ImportError:
    DATABASE_URL = None


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
    asyncpg.connect() does NOT accept libpq-style query params like sslmode/channel_binding.
    If present, SQLAlchemy asyncpg dialect forwards them as kwargs -> TypeError.
    We remove them and enforce TLS via connect_args.
    """
    parts = urlsplit(url)
    q = [
        (k, v)
        for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in {"sslmode", "channel_binding"}
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(q, doseq=True), parts.fragment)
    )


# Détermination de l'URL de base de données
connect_args = {}

if DATABASE_URL:
    FINAL_URL = _to_asyncpg_sqlalchemy_url(DATABASE_URL)

    # Si on utilise asyncpg, on nettoie l'URL et on force SSL via connect_args
    if FINAL_URL.startswith("postgresql+asyncpg://"):
        FINAL_URL = _sanitize_asyncpg_url(FINAL_URL)
        connect_args = {"ssl": ssl.create_default_context()}
else:
    # Fallback sur SQLite uniquement si aucune DATABASE_URL n'est définie
    print("⚠️ Aucune DATABASE_URL trouvée, utilisation de SQLite par défaut")
    FINAL_URL = "sqlite+aiosqlite:///./test.db"

print(f"🔗 Connexion à la base de données : {FINAL_URL.split('@')[-1] if '@' in FINAL_URL else FINAL_URL}")

engine = create_async_engine(FINAL_URL, echo=False, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Event listener pour SQLite uniquement (active les clés étrangères)
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Vérifie si c'est une connexion SQLite
    if "sqlite" in str(type(dbapi_connection)).lower():
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()