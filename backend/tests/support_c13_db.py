"""Live-Postgres append-only scenario for C-13 (skips without PG)."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Import every model package so Base.metadata can sort FKs (incl. turno).
import app.domain.agenda.models  # noqa: F401,E402
import app.domain.clinica.models  # noqa: F401,E402
import app.domain.notificaciones.models  # noqa: F401,E402
import app.domain.pacientes.models  # noqa: F401,E402
from app.domain.models import Base
from app.shared.settings import get_settings

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _append_only_statements() -> list[str]:
    path = next(
        p for p in VERSIONS.glob("*.py") if "c13a1b2c3d4e5" in p.name
    )
    spec = importlib.util.spec_from_file_location("c13_migration_db", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._append_only_upgrade_sql()


async def _set_tenant(conn, tenant_id: uuid.UUID) -> None:  # type: ignore[no-untyped-def]
    await conn.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


async def run_append_only_scenario() -> None:
    """Create an event, then prove DB triggers reject UPDATE and DELETE."""
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "DROP TRIGGER IF EXISTS evento_pieza_no_delete "
                    "ON evento_pieza"
                )
            )
            await conn.execute(
                text(
                    "DROP TRIGGER IF EXISTS evento_pieza_no_update "
                    "ON evento_pieza"
                )
            )
            for statement in _append_only_statements():
                await conn.execute(text(statement))

        tenant_id = uuid.uuid4()
        usuario_id = uuid.uuid4()
        paciente_id = uuid.uuid4()
        historia_id = uuid.uuid4()
        odontograma_id = uuid.uuid4()
        evento_id = uuid.uuid4()

        async with engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            await conn.execute(
                text(
                    "INSERT INTO tenant (id, slug_reserva, nombre) "
                    "VALUES (:id, :slug, :nombre)"
                ),
                {
                    "id": str(tenant_id),
                    "slug": f"c13-{tenant_id.hex[:12]}",
                    "nombre": "Tenant Ficticio C-13",
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO usuario (id, tenant_id, email) "
                    "VALUES (:id, :tid, :email)"
                ),
                {
                    "id": str(usuario_id),
                    "tid": str(tenant_id),
                    "email": f"u-{usuario_id.hex[:8]}@demo-ficticia.invalid",
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO paciente (id, tenant_id, nombre, telefono) "
                    "VALUES (:id, :tid, :nombre, :tel)"
                ),
                {
                    "id": str(paciente_id),
                    "tid": str(tenant_id),
                    "nombre": "Paciente Ficticio C-13",
                    "tel": "+5491100000000",
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO historia_clinica "
                    "(id, tenant_id, paciente_id) VALUES (:id, :tid, :pid)"
                ),
                {
                    "id": str(historia_id),
                    "tid": str(tenant_id),
                    "pid": str(paciente_id),
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO odontograma "
                    "(id, tenant_id, historia_clinica_id) "
                    "VALUES (:id, :tid, :hid)"
                ),
                {
                    "id": str(odontograma_id),
                    "tid": str(tenant_id),
                    "hid": str(historia_id),
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO evento_pieza "
                    "(id, tenant_id, odontograma_id, pieza_fdi, superficie, "
                    "estado, autor_usuario_id) "
                    "VALUES (:id, :tid, :oid, 16, 'oclusal', 'caries', :uid)"
                ),
                {
                    "id": str(evento_id),
                    "tid": str(tenant_id),
                    "oid": str(odontograma_id),
                    "uid": str(usuario_id),
                },
            )

        update_ok = False
        try:
            async with engine.begin() as conn:
                await _set_tenant(conn, tenant_id)
                await conn.execute(
                    text("UPDATE evento_pieza SET estado = 'sano' WHERE id = :id"),
                    {"id": str(evento_id)},
                )
            update_ok = True
        except Exception:
            pass
        assert not update_ok, "UPDATE on evento_pieza must be rejected"

        delete_ok = False
        try:
            async with engine.begin() as conn:
                await _set_tenant(conn, tenant_id)
                await conn.execute(
                    text("DELETE FROM evento_pieza WHERE id = :id"),
                    {"id": str(evento_id)},
                )
            delete_ok = True
        except Exception:
            pass
        assert not delete_ok, "DELETE on evento_pieza must be rejected"

        async with engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            estado = (
                await conn.execute(
                    text("SELECT estado FROM evento_pieza WHERE id = :id"),
                    {"id": str(evento_id)},
                )
            ).scalar_one()
        assert estado == "caries"
    finally:
        await engine.dispose()
