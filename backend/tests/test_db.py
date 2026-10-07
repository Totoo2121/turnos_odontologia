"""Async DB session tests (C-01 task 1.4) — no live DB required for engine shape."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_engine_uses_asyncpg_driver() -> None:
    """WHEN settings loaded THEN engine is created with the asyncpg driver."""
    from app.shared.db import create_engine_from_settings

    engine = create_engine_from_settings()
    try:
        assert "asyncpg" in engine.url.drivername
        assert engine.url.database == "fake_db"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_factory_yields_async_session() -> None:
    """WHEN session factory used THEN it produces an AsyncSession without connecting."""
    from app.shared.db import create_engine_from_settings, create_session_factory

    engine = create_engine_from_settings()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            assert isinstance(session, AsyncSession)
    finally:
        await engine.dispose()


def test_metadata_naming_convention_is_lowercase() -> None:
    """WHEN metadata inspected THEN naming convention keys are lowercase identifiers."""
    from app.shared.db import NAMING_CONVENTION

    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}
    assert all(k == k.lower() for k in NAMING_CONVENTION)
