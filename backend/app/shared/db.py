"""Async SQLAlchemy 2.0 session (engine + dependency, modest pool, no domain models)."""

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.shared.settings import get_settings

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine_from_settings() -> AsyncEngine:
    """Create the async engine from settings (modest pool, short transactions)."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the engine (no autocommit sprawl)."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide engine (lazy singleton)."""
    global _engine
    if _engine is None:
        _engine = create_engine_from_settings()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory (lazy singleton)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one short-lived async session per request."""
    async with get_session_factory()() as session:
        try:
            yield session
        finally:
            await session.close()


def engine_kwargs_for_tests(**overrides: Any) -> dict[str, Any]:
    """Expose pool defaults for tests/docs (no connection opened)."""
    base: dict[str, Any] = {
        "pool_size": 5,
        "max_overflow": 5,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    base.update(overrides)
    return base
