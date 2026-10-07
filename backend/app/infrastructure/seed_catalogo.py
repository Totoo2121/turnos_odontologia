"""C-05 catalog seed (D7): prestaciones, Box, profesional demo y feriados.

Todo valor es sintetico y ficticio (nombres marcados ``(ficticia/o)`` o
``(demo)``, matricula ``MN-00000``, dominio ``.invalid`` donde aplica).
Idempotente: upsert por claves naturales — ``(tenant_id, nombre)`` en
prestaciones/sillon/profesional, par ``(profesional_id, prestacion_id)`` en
habilitaciones y ``(tenant_id, profesional_id, inicio)`` en bloqueos — seguro
re-ejecutar en cada deploy. Las filas existentes NO se pisan (respeta edicion
del duenio); solo se agregan las faltantes. Commitear es trabajo del llamador.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

Row = dict[str, Any]

# Las 5 prestaciones ejemplo del change (duraciones/buffers/precios ARS
# ficticios; moneda fija ARS por RN-AD-01).
PRESTACIONES_EJEMPLO: tuple[Row, ...] = (
    {
        "nombre": "Consulta (ficticia)",
        "duracion_min": 30,
        "buffer_min": 0,
        "requiere_sillon": False,
        "permite_sobreturno": False,
        "sena_obligatoria": False,
        "monto_sena": None,
        "anticipacion_min_cancel_hs": 24,
        "precio": "8000.00",
    },
    {
        "nombre": "Limpieza (ficticia)",
        "duracion_min": 45,
        "buffer_min": 10,
        "requiere_sillon": True,
        "permite_sobreturno": False,
        "sena_obligatoria": False,
        "monto_sena": None,
        "anticipacion_min_cancel_hs": 24,
        "precio": "15000.00",
    },
    {
        "nombre": "Conducto (ficticia)",
        "duracion_min": 90,
        "buffer_min": 15,
        "requiere_sillon": True,
        "permite_sobreturno": False,
        "sena_obligatoria": True,
        "monto_sena": "10000.00",
        "anticipacion_min_cancel_hs": 48,
        "precio": "45000.00",
    },
    {
        "nombre": "Corona (ficticia)",
        "duracion_min": 60,
        "buffer_min": 10,
        "requiere_sillon": True,
        "permite_sobreturno": True,
        "sena_obligatoria": True,
        "monto_sena": "12000.00",
        "anticipacion_min_cancel_hs": 48,
        "precio": "60000.00",
    },
    {
        "nombre": "Ortodoncia control (ficticia)",
        "duracion_min": 30,
        "buffer_min": 5,
        "requiere_sillon": True,
        "permite_sobreturno": False,
        "sena_obligatoria": False,
        "monto_sena": None,
        "anticipacion_min_cancel_hs": 24,
        "precio": "10000.00",
    },
)

SILLON_EJEMPLO: Row = {"nombre": "Box 1 (demo)", "activo": True}

PROFESIONAL_EJEMPLO: Row = {
    "nombre": "Dr. Demo (ficticio)",
    "matricula": "MN-00000 (ficticia)",
    "especialidades": ["Odontologia general (ficticia)"],
    "duracion_default_min": 30,
    "activo": True,
}

# Feriados nacionales AR como EJEMPLO estatico (mes, dia) por anio. No es
# fuente oficial: el calendario real cambia por decreto cada anio.
FERIADOS_EJEMPLO_AR: dict[int, list[tuple[int, int]]] = {
    2026: [
        (1, 1),  # Anio Nuevo
        (2, 16),  # Carnaval (ejemplo)
        (2, 17),  # Carnaval (ejemplo)
        (3, 24),  # Memoria
        (4, 2),  # Malvinas + Jueves Santo (ejemplo)
        (4, 3),  # Viernes Santo (ejemplo)
        (5, 1),  # Trabajador
        (5, 25),  # Revolucion de Mayo
        (6, 20),  # Belgrano
        (7, 9),  # Independencia
        (12, 8),  # Inmaculada
        (12, 25),  # Navidad
    ],
    2027: [
        (1, 1),
        (3, 24),
        (4, 2),
        (5, 1),
        (5, 25),
        (6, 20),
        (7, 9),
        (12, 8),
        (12, 25),
    ],
}


def feriados_del_ano(year: int) -> list[tuple[datetime, datetime]]:
    """Ventanas full-day UTC de los feriados ejemplo del anio pedido."""
    dias = FERIADOS_EJEMPLO_AR.get(year, FERIADOS_EJEMPLO_AR[2026])
    ventanas = []
    for mes, dia in dias:
        inicio = datetime(year, mes, dia, 0, 0, tzinfo=UTC)
        ventanas.append((inicio, inicio + timedelta(days=1)))
    return ventanas


async def seed_catalogo(store: Any, *, year: int) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Crea el catalogo demo del tenant (idempotente, re-ejecutable).

    Politica de feriados: la lista ``FERIADOS_EJEMPLO_AR`` es un EJEMPLO
    estatico y **no es fuente oficial** del calendario argentino. Para
    recargar un anio nuevo, agregar su entrada a ``FERIADOS_EJEMPLO_AR`` y
    re-ejecutar este seed (solo agrega bloqueos faltantes; los duenios
    pueden editar/borrar bloqueos por API en cualquier momento).

    Returns ``{"prestaciones": 5, "sillones": 1, "profesionales": 1,
    "bloqueos": N}`` con los conteos resultantes del tenant.
    Commitear es trabajo del llamador.
    """
    existentes_prest = {
        row["nombre"]: row
        for row in await store.list_prestaciones(limit=500, offset=0)
    }
    for data in PRESTACIONES_EJEMPLO:
        if data["nombre"] not in existentes_prest:
            created = await store.create_prestacion(dict(data))
            existentes_prest[created["nombre"]] = created

    existentes_sillon = {
        row["nombre"]: row for row in await store.list_sillones(limit=500, offset=0)
    }
    if SILLON_EJEMPLO["nombre"] not in existentes_sillon:
        created = await store.create_sillon(dict(SILLON_EJEMPLO))
        existentes_sillon[created["nombre"]] = created

    existentes_prof = {
        row["nombre"]: row
        for row in await store.list_profesionales(limit=500, offset=0)
    }
    if PROFESIONAL_EJEMPLO["nombre"] not in existentes_prof:
        data = dict(PROFESIONAL_EJEMPLO)
        created = await store.create_profesional(data)
        existentes_prof[created["nombre"]] = created
    profesional = existentes_prof[PROFESIONAL_EJEMPLO["nombre"]]

    prestacion_ids = [row["id"] for row in existentes_prest.values()]
    await store.set_habilitaciones(profesional["id"], prestacion_ids)

    existentes_bloq = {
        (row.get("profesional_id"), row["inicio"])
        for row in await store.list_bloqueos(limit=1000, offset=0)
    }
    for inicio, fin in feriados_del_ano(year):
        if (profesional["id"], inicio) not in existentes_bloq:
            await store.create_bloqueo(
                {
                    "profesional_id": profesional["id"],
                    "sillon_id": None,
                    "inicio": inicio,
                    "fin": fin,
                    "motivo": "feriado",
                }
            )

    bloqueos = await store.list_bloqueos(limit=1000, offset=0)
    return {
        "prestaciones": len(existentes_prest),
        "sillones": len(existentes_sillon),
        "profesionales": len(existentes_prof),
        "bloqueos": len(bloqueos),
    }


async def seed_catalogo_session(session: Any, tenant_id: uuid.UUID, *, year: int) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Wrapper de sesion SQLAlchemy (produccion/CLI) sobre el seed por puerto."""
    from app.application.catalog_store import DbCatalogStore

    return await seed_catalogo(DbCatalogStore(session, tenant_id), year=year)


async def main() -> None:
    """CLI: ``python -m app.infrastructure.seed_catalogo`` desde backend/.

    Requiere ``TENANT_ID`` (uuid del tenant demo) y ``YEAR`` opcional.
    """
    import os

    from app.shared.db import create_engine_from_settings, create_session_factory

    tenant_id = uuid.UUID(os.environ["TENANT_ID"])
    year = int(os.environ.get("YEAR", "2026"))
    engine = create_engine_from_settings()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            summary = await seed_catalogo_session(session, tenant_id, year=year)
            await session.commit()
        print(f"seed_catalogo ok: {summary} (all values fictitious)")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
