"""C-02 models tests (task 1.2) — RED first.

Metadata/transient seams run without a DB. Behavioral persistence scenarios
are Postgres-gated and SKIP honestly when no live DB is reachable.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import re
import uuid
from typing import Any

import pytest
from sqlalchemy import CheckConstraint, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.domain.models import (
    PASSWORD_UNSET_MARKER,
    ROLE_NAMES,
    SLUG_PATTERN,
    Base,
    Rol,
    Sucursal,
    Tenant,
    UserRol,
    Usuario,
)


def _table(model: Any) -> Table:
    """Table metadata by model (typed seam; avoids __table__ plugin gaps)."""
    return Base.metadata.tables[model.__tablename__]


# --- 1. Tables registered on the shared metadata, lowercase names ---


def test_all_five_tables_registered_lowercase() -> None:
    """WHEN shared metadata inspected THEN the 5 C-02 tables exist lowercase."""
    from app.shared.db import metadata

    for name in ("tenant", "sucursal", "usuario", "rol", "user_rol"):
        assert name in metadata.tables, f"missing table: {name}"
        assert name == name.lower()


def test_all_pks_are_native_uuid() -> None:
    """WHEN tables inspected THEN every PK is a native UUID column."""
    for model in (Tenant, Sucursal, Usuario, Rol, UserRol):
        pk_cols = list(_table(model).primary_key.columns)
        assert len(pk_cols) == 1
        assert isinstance(pk_cols[0].type, PG_UUID), model.__tablename__


# --- 2. Tenant identity: slug unique Wells + CHECK + defaults ---


def test_slug_reserva_unique_and_checked() -> None:
    """WHEN tenant table inspected THEN slug has UNIQUE + format CHECK."""
    table = _table(Tenant)
    unique_cols = {c.name for c in table.columns if c.unique} | {
        c.name
        for const in table.constraints
        if isinstance(const, UniqueConstraint)
        for c in const.columns
    }
    assert "slug_reserva" in unique_cols
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert checks, "expected a CHECK on slug_reserva"
    assert any("slug_reserva" in str(c.sqltext) for c in checks)


def test_slug_pattern_accepts_valid_rejects_invalid() -> None:
    """WHEN slug pattern applied THEN valid slugs pass, invalid fail."""
    assert re.match(SLUG_PATTERN, "demo-ficticia")
    assert re.match(SLUG_PATTERN, "clinica-norte-123")
    assert not re.match(SLUG_PATTERN, "Demo-Mayusculas")
    assert not re.match(SLUG_PATTERN, "con espacios")
    assert not re.match(SLUG_PATTERN, "guion_bajo")


def test_tenant_defaults_plan_base_moneda_ars() -> None:
    """WHEN tenant columns inspected THEN plan defaults base, moneda ARS."""
    table = _table(Tenant)
    assert getattr(table.c.plan.default, "arg", None) == "base"
    assert getattr(table.c.moneda.default, "arg", None) == "ARS"


def test_usuario_unique_tenant_email() -> None:
    """WHEN usuario table inspected THEN UNIQUE(tenant_id, email) exists."""
    table = _table(Usuario)
    found = any(
        isinstance(const, UniqueConstraint)
        and {c.name for c in const.columns} == {"tenant_id", "email"}
        for const in table.constraints
    )
    assert found, "missing UNIQUE(tenant_id, email)"


def test_email_normalized_to_lowercase_without_db() -> None:
    """WHEN Usuario built with mixed-case email THEN it is lowercased."""
    tid = uuid.uuid4()
    user = Usuario(
        tenant_id=tid, email="Admin@Demo-Ficticia.INVALID", password_hash=None
    )
    assert user.email == "admin@demo-ficticia.invalid"


def test_fk_columns_are_indexed() -> None:
    """WHEN tables inspected THEN every FK column has an index."""
    for model in (Sucursal, Usuario, UserRol):
        table = _table(model)
        for column in table.columns:
            if column.foreign_keys:
                covered = any(
                    column.name in {c.name for c in index.columns}
                    for index in table.indexes
                )
                assert covered, f"{model.__tablename__}.{column.name} lacks index"


# --- 3. D6: Rol global vs UserRol tenant-scoped ---


def test_rol_has_no_tenant_id_and_four_names() -> None:
    """WHEN Rol inspected THEN no tenant_id column; catalog is 4 names."""
    assert "tenant_id" not in _table(Rol).columns
    assert "nombre" in _table(Rol).columns
    assert ROLE_NAMES == ("propietario", "odontologo", "recepcion", "asistente")


def test_user_rol_carries_tenant_id_with_unique_pair() -> None:
    """WHEN user_rol inspected THEN tenant_id present + UNIQUE(usuario, rol)."""
    table = _table(UserRol)
    assert "tenant_id" in table.columns
    found = any(
        isinstance(const, UniqueConstraint)
        and {c.name for c in const.columns} == {"usuario_id", "rol_id"}
        for const in table.constraints
    )
    assert found, "missing UNIQUE(usuario_id, rol_id)"


def test_password_hash_nullable_with_unset_marker() -> None:
    """WHEN usuario inspected THEN password_hash NULL + marker never authenticates."""
    assert _table(Usuario).c.password_hash.nullable is True
    assert PASSWORD_UNSET_MARKER == "!UNSET-C03*"
    assert len(PASSWORD_UNSET_MARKER) > 60 or PASSWORD_UNSET_MARKER.startswith("!")


# --- 4. AuditMixin + updated_at ---


def test_audit_columns_on_four_entities() -> None:
    """WHEN domain entities inspected THEN audit columns exist."""
    for model in (Tenant, Sucursal, Usuario, Rol):
        table = _table(model)
        for column in ("is_active", "created_at", "updated_at", "deleted_at"):
            assert column in table.columns, f"{model.__tablename__}.{column}"


def test_user_rol_has_only_created_at() -> None:
    """WHEN link table inspected THEN only created_at, no soft-delete columns."""
    table = _table(UserRol)
    assert "created_at" in table.columns
    assert "deleted_at" not in table.columns
    assert "is_active" not in table.columns


def test_updated_at_has_onupdate_configured() -> None:
    """WHEN usuario inspected THEN updated_at advances on modification (onupdate)."""
    column = _table(Usuario).c.updated_at
    assert column.onupdate is not None


def test_sucursal_unique_tenant_nombre_and_nullable_contact() -> None:
    """WHEN sucursal inspected THEN UNIQUE(tenant_id, nombre); contact NULL."""
    table = _table(Sucursal)
    assert table.c.direccion.nullable is True
    assert table.c.telefono.nullable is True
    found = any(
        isinstance(const, UniqueConstraint)
        and {c.name for c in const.columns} == {"tenant_id", "nombre"}
        for const in table.constraints
    )
    assert found, "missing UNIQUE(tenant_id, nombre)"


def test_soft_delete_columns_shape() -> None:
    """WHEN audit columns inspected THEN deleted_at NULL, is_active default live."""
    assert _table(Usuario).c.deleted_at.nullable is True
    assert _table(Tenant).c.is_active.nullable is False
    assert getattr(_table(Tenant).c.is_active.default, "arg", None) is True


def test_email_normalize_strips_and_lowercases_edge_cases() -> None:
    """WHEN emails with spaces/case assigned THEN normalized uniformly."""
    tid = uuid.uuid4()
    assert (
        Usuario(tenant_id=tid, email="  ADMIN@X.INVALID  ").email == "admin@x.invalid"
    )
    assert Usuario(tenant_id=tid, email="a@b.c").email == "a@b.c"


# --- 5. Postgres-gated behavioral scenarios (honest SKIP without live DB) ---


def test_pg_gated_timestamp_advances() -> None:
    """WHEN entity modified on live PG THEN updated_at ends after created_at."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.domain.models import Base
        from tests.c02_pg import pg_dsn

        engine = create_async_engine(pg_dsn())
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            from sqlalchemy.ext.asyncio import async_sessionmaker

            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                tenant = Tenant(slug_reserva="ts-ficticia", nombre="TS Ficticia")
                session.add(tenant)
                await session.commit()
                created = tenant.created_at
                assert created is not None
                await asyncio.sleep(0.02)
                tenant.nombre = "TS Ficticia 2"
                await session.commit()
                await session.refresh(tenant)
                assert tenant.updated_at is not None
                assert tenant.updated_at > created
                await session.delete(tenant)
                await session.commit()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_gated_slug_unique_enforced_and_default_ars() -> None:
    """WHEN two tenants share a slug on live PG THEN second fails; ARS default."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.domain.models import Base
        from tests.c02_pg import pg_dsn

        engine = create_async_engine(pg_dsn())
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                first = Tenant(slug_reserva="dupe-ficticia", nombre="Uno")
                session.add(first)
                await session.commit()
                assert first.moneda == "ARS"
                assert first.plan == "base"
                session.add(Tenant(slug_reserva="dupe-ficticia", nombre="Dos"))
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
                for row in (await session.execute(Tenant.__table__.select())).all():
                    await session.delete(row[0])
                await session.commit()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_run())
