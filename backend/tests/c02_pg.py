"""Shared Postgres probe for C-02 DB-gated tests (skip when unreachable).

Live-DB tests (isolation, RLS enforcement, persistence round-trips) require a
real PostgreSQL 15+. On machines without one (no Docker daemon, no service)
they SKIP honestly — CI runs them. Never fake a green.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import asyncio

DIALECT_PREFIX = "postgresql+asyncpg://"
PLAIN_PREFIX = "postgresql://"


def pg_dsn() -> str:
    """Return the probe DSN derived from DATABASE_URL (asyncpg form)."""
    from app.shared.settings import get_settings

    url = get_settings().database_url
    if url.startswith(DIALECT_PREFIX):
        return PLAIN_PREFIX + url[len(DIALECT_PREFIX) :]
    return url


async def _can_connect(dsn: str) -> bool:
    try:
        import asyncpg

        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=2)
        await conn.close()
        return True
    except Exception:
        return False


def pg_available() -> bool:
    """Probe Postgres reachability with a short timeout (no side effects)."""
    return asyncio.run(_can_connect(pg_dsn()))
