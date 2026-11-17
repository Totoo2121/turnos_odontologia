"""Live-Postgres append-only scenario for C-12 (skips honestly without PG)."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Import every model package so Base.metadata can sort FKs (incl. turno).
import app.domain.agenda.models  # noqa: F401,E402
import app.domain.notificaciones.models  # noqa: F401,E402
import app.domain.pacientes.models  # noqa: F401,E402
from app.domain.models import Base
from app.shared.settings import get_settings

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _append_only_statements() -> list[str]:
    path = next(
        p for p in VERSIONS.glob("*.py") if "c12a1b2c3d4e5" in p.name
    )
    spec = importlib.util.spec_from_file_location("c12_migration_db", path)
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
    """Create an evolution, then prove DB triggers reject UPDATE and DELETE."""
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text("DROP TRIGGER IF EXISTS evolucion_no_delete ON evolucion")
            )
            await conn.execute(
                text("DROP TRIGGER IF EXISTS evolucion_no_update ON evolucion")
            )
            for statement in _append_only_statements():
                await conn.execute(text(statement))

        tenant_id = uuid.uuid4()
        usuario_id = uuid.uuid4()
        paciente_id = uuid.uuid4()
        historia_id = uuid.uuid4()
        evolucion_id = uuid.uuid4()

        async with engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            await conn.execute(
                text(
                    "INSERT INTO tenant (id, slug_reserva, nombre) "
                    "VALUES (:id, :slug, :nombre)"
                ),
                {
                    "id": str(tenant_id),
                    "slug": f"c12-{tenant_id.hex[:12]}",
                    "nombre": "Tenant Ficticio C-12",
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
                    "nombre": "Paciente Ficticio C-12",
                    "tel": "+5491100000000",
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO historia_clinica "
                    "(id, tenant_id, paciente_id) "
                    "VALUES (:id, :tid, :pid)"
                ),
                {
                    "id": str(historia_id),
                    "tid": str(tenant_id),
                    "pid": str(paciente_id),
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO evolucion "
                    "(id, tenant_id, historia_clinica_id, "
                    "autor_usuario_id, contenido) "
                    "VALUES (:id, :tid, :hid, :uid, :texto)"
                ),
                {
                    "id": str(evolucion_id),
                    "tid": str(tenant_id),
                    "hid": str(historia_id),
                    "uid": str(usuario_id),
                    "texto": "Evolucion original ficticia",
                },
            )

        update_ok = False
        try:
            async with engine.begin() as conn:
                await _set_tenant(conn, tenant_id)
                await conn.execute(
                    text(
                        "UPDATE evolucion SET contenido = :texto "
                        "WHERE id = :id"
                    ),
                    {"texto": "hackeada", "id": str(evolucion_id)},
                )
            update_ok = True
        except Exception:
            pass
        assert not update_ok, "UPDATE on evolucion must be rejected"

        delete_ok = False
        try:
            async with engine.begin() as conn:
                await _set_tenant(conn, tenant_id)
                await conn.execute(
                    text("DELETE FROM evolucion WHERE id = :id"),
                    {"id": str(evolucion_id)},
                )
            delete_ok = True
        except Exception:
            pass
        assert not delete_ok, "DELETE on evolucion must be rejected"

        async with engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            contenido = (
                await conn.execute(
                    text(
                        "SELECT contenido FROM evolucion WHERE id = :id"
                    ),
                    {"id": str(evolucion_id)},
                )
            ).scalar_one()
        assert contenido == "Evolucion original ficticia"
    finally:
        await engine.dispose()
