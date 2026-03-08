import os, asyncio, ssl
import asyncpg
from urllib.parse import urlparse

async def main():
    raw = os.environ["DATABASE_URL"]

    u = urlparse(raw)
    if u.scheme not in ("postgresql", "postgres"):
        raise SystemExit(f"Expected postgresql:// or postgres://, got {u.scheme!r}")

    ssl_ctx = ssl.create_default_context()

    conn = await asyncpg.connect(
        user=u.username,
        password=u.password,
        host=u.hostname,
        port=u.port or 5432,
        database=(u.path or "").lstrip("/") or "postgres",
        ssl=ssl_ctx,
    )
    try:
        print("SELECT 1 =>", await conn.fetchval("SELECT 1;"))
        row = await conn.fetchrow("SELECT current_user, current_database();")
        print("user/db =>", dict(row))
    finally:
        await conn.close()

asyncio.run(main())