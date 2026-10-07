"""Live-Postgres support for the C-03 migration 002 cycle.

Mirrors `support_c02_db` helpers for the 001↔002 range. Only imported by
Postgres-gated tests that already skipped when no DB is reachable.
"""

from __future__ import annotations

REVISION_001 = "c02a1b2c3d4e5"
REVISION_002 = "c03a1b2c3d4e5"


async def alembic_upgrade_002(sqlalchemy_url: str) -> None:
    """Apply migrations up to the C-03 head (002) on the target DB."""
    from alembic import command
    from tests.support_c02_db import _alembic_config, _with_database_url

    with _with_database_url(sqlalchemy_url):
        command.upgrade(_alembic_config(sqlalchemy_url), REVISION_002)


async def alembic_downgrade_001(sqlalchemy_url: str) -> None:
    """Downgrade back to the C-02 head (removes the 2 C-03 tables)."""
    from alembic import command
    from tests.support_c02_db import _alembic_config, _with_database_url

    with _with_database_url(sqlalchemy_url):
        command.downgrade(_alembic_config(sqlalchemy_url), REVISION_001)
