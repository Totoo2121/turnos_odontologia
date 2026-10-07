"""C-03 model tests (task 3.1) — RED first.

`RevokedToken` (global, no tenant, no RLS — second explicit exception, D6)
and `PortalToken` (tenant-scoped + RLS). Metadata-only assertions run without
a live DB; DDL/RLS enforcement is Postgres-gated in `test_c03_migration.py`.
"""

from __future__ import annotations


def test_models_import_without_cycles() -> None:
    """WHEN domain models imported THEN no import cycle and both models exist."""
    import app.domain.models as models

    assert hasattr(models, "RevokedToken")
    assert hasattr(models, "PortalToken")


def test_revoked_token_is_global_without_tenant() -> None:
    """WHEN revoked_token inspected THEN no tenant_id (D6 exception)."""
    from app.domain.models import RevokedToken

    columns = set(RevokedToken.__table__.columns.keys())
    assert "tenant_id" not in columns
    assert RevokedToken.__tablename__ == "revoked_token"
    assert isinstance(RevokedToken.__table__.c.jti.primary_key, bool)
    assert RevokedToken.__table__.c.jti.primary_key is True
    for required in ("type", "expires_at", "reason", "created_at"):
        assert required in columns, required


def test_portal_token_is_tenant_scoped() -> None:
    """WHEN portal_token inspected THEN tenant_id FK + unique jti + RLS shape."""
    from app.domain.models import PortalToken

    table = PortalToken.__table__
    columns = set(table.columns.keys())
    assert PortalToken.__tablename__ == "portal_token"
    for required in (
        "id",
        "tenant_id",
        "turno_id",
        "jti",
        "expires_at",
        "revoked_at",
        "created_at",
    ):
        assert required in columns, required
    assert table.c.tenant_id.nullable is False
    assert table.c.turno_id.nullable is False
    unique_cols = {
        tuple(c.name for c in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("jti",) in unique_cols
    fk_targets = {
        tuple(c.target_fullname for c in constraint.elements)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "ForeignKeyConstraint"
    }
    assert any("tenant.id" in targets for targets in fk_targets)
    assert table.indexes, "portal_token needs FK/lookup indexes"


def test_tablenames_lowercase() -> None:
    """WHEN table names read THEN all lowercase (project convention)."""
    from app.domain.models import PortalToken, RevokedToken

    assert RevokedToken.__tablename__ == RevokedToken.__tablename__.lower()
    assert PortalToken.__tablename__ == PortalToken.__tablename__.lower()


def test_new_tables_registered_on_shared_metadata() -> None:
    """WHEN shared metadata inspected THEN both tables visible to alembic."""
    from app.domain.models import Base

    assert "revoked_token" in Base.metadata.tables
    assert "portal_token" in Base.metadata.tables
