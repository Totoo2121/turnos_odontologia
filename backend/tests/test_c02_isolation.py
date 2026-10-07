"""C-02 isolation tests RN-SE-01 (task 2.2).

The global-catalog metadata assertion runs without a DB. Every behavioral
scenario needs live Postgres (RLS + data) and SKIPs honestly otherwise.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.domain.models import Rol


def test_rol_table_carries_no_tenant_data() -> None:
    """WHEN rol table inspected THEN no tenant_id, no email, no PII columns."""
    columns = set(Rol.__table__.columns.keys())
    assert "tenant_id" not in columns
    assert "email" not in columns
    assert "password_hash" not in columns
    assert {"nombre", "descripcion"} <= columns


def test_pg_gated_cross_tenant_list_is_empty() -> None:
    """WHEN tenant A lists on live PG THEN no rows of tenant B appear."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    from tests.support_c02_isolation import run_isolation_scenario

    asyncio.run(run_isolation_scenario("list_empty"))


def test_pg_gated_cross_tenant_get_is_denied() -> None:
    """WHEN tenant A reads B's id on live PG THEN treated as nonexistent."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    from tests.support_c02_isolation import run_isolation_scenario

    asyncio.run(run_isolation_scenario("get_denied"))


def test_pg_gated_cross_tenant_write_is_denied() -> None:
    """WHEN tenant A deletes B's row on live PG THEN denied, row survives."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    from tests.support_c02_isolation import run_isolation_scenario

    asyncio.run(run_isolation_scenario("write_denied"))
