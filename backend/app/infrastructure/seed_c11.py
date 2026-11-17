"""C-11 seed: approved WhatsApp/email templates per tenant (idempotent).

All texts are synthetic examples (fictitious). Re-running the seed only adds
missing ``(clave, canal, idioma, version)`` rows; it never overwrites an
existing active version edited by the tenant.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.application.notificaciones import (
    CANAL_EMAIL,
    CANAL_WHATSAPP,
    PlantillaRecord,
    PlantillaStore,
)

Row = dict[str, Any]

PLANTILLAS_C11: tuple[Row, ...] = (
    {
        "clave": "recordatorio_t48h",
        "canal": CANAL_WHATSAPP,
        "meta_template_name": "recordatorio_turno_48h",
        "cuerpo": (
            "Hola, te recordamos tu turno del {fecha} a las {hora}. "
            "Respondé CONFIRMAR para confirmarlo."
        ),
    },
    {
        "clave": "recordatorio_t48h",
        "canal": CANAL_EMAIL,
        "meta_template_name": None,
        "cuerpo": (
            "Hola:\n\nTe recordamos tu turno del {fecha} a las {hora}.\n"
            "Podés confirmarlo desde el portal del paciente.\n\n"
            "Este mensaje es un ejemplo ficticio."
        ),
    },
    {
        "clave": "recordatorio_t24h",
        "canal": CANAL_WHATSAPP,
        "meta_template_name": "recordatorio_turno_24h",
        "cuerpo": (
            "Tu turno es mañana a las {hora}. Respondé CONFIRMAR para "
            "reservar tu lugar."
        ),
    },
    {
        "clave": "recordatorio_t24h",
        "canal": CANAL_EMAIL,
        "meta_template_name": None,
        "cuerpo": (
            "Hola:\n\nTu turno es mañana a las {hora}.\n"
            "Confirmalo desde el portal del paciente.\n\n"
            "Este mensaje es un ejemplo ficticio."
        ),
    },
    {
        "clave": "confirmacion",
        "canal": CANAL_WHATSAPP,
        "meta_template_name": "confirmacion_turno",
        "cuerpo": "Tu turno del {fecha} a las {hora} quedó confirmado. ¡Gracias!",
    },
    {
        "clave": "confirmacion",
        "canal": CANAL_EMAIL,
        "meta_template_name": None,
        "cuerpo": (
            "Hola:\n\nTu turno del {fecha} a las {hora} quedó confirmado.\n\n"
            "Este mensaje es un ejemplo ficticio."
        ),
    },
    {
        "clave": "recall_ausente",
        "canal": CANAL_WHATSAPP,
        "meta_template_name": "recall_ausente",
        "cuerpo": (
            "Notamos que no pudiste asistir a tu turno. ¿Querés que te "
            "ofrezcamos un nuevo horario? Respondé REPROGRAMAR."
        ),
    },
    {
        "clave": "recall_ausente",
        "canal": CANAL_EMAIL,
        "meta_template_name": None,
        "cuerpo": (
            "Hola:\n\nNotamos que no pudiste asistir a tu turno.\n"
            "Respondé este correo y te ofrecemos un nuevo horario.\n\n"
            "Este mensaje es un ejemplo ficticio."
        ),
    },
    {
        "clave": "control",
        "canal": CANAL_WHATSAPP,
        "meta_template_name": "control_periodico",
        "cuerpo": (
            "Ya pasó el tiempo recomendado para tu control. "
            "Escribinos para coordinar un nuevo turno."
        ),
    },
    {
        "clave": "control",
        "canal": CANAL_EMAIL,
        "meta_template_name": None,
        "cuerpo": (
            "Hola:\n\nYa pasó el tiempo recomendado para tu control.\n"
            "Escribinos para coordinar un nuevo turno.\n\n"
            "Este mensaje es un ejemplo ficticio."
        ),
    },
    {
        "clave": "aviso_recepcion",
        "canal": CANAL_WHATSAPP,
        "meta_template_name": "aviso_recepcion",
        "cuerpo": (
            "Aviso interno: hay turnos sin confirmar que requieren "
            "seguimiento de recepción."
        ),
    },
    {
        "clave": "aviso_recepcion",
        "canal": CANAL_EMAIL,
        "meta_template_name": None,
        "cuerpo": (
            "Aviso interno: hay turnos sin confirmar que requieren "
            "seguimiento de recepción."
        ),
    },
    {
        "clave": "politica_cancelacion",
        "canal": CANAL_WHATSAPP,
        "meta_template_name": "politica_cancelacion",
        "cuerpo": (
            "Política de cancelación: podés cancelar o reprogramar hasta "
            "{anticipacion_hs} horas antes del turno."
        ),
    },
    {
        "clave": "politica_cancelacion",
        "canal": CANAL_EMAIL,
        "meta_template_name": None,
        "cuerpo": (
            "Política de cancelación: podés cancelar o reprogramar hasta "
            "{anticipacion_hs} horas antes del turno.\n\n"
            "Este mensaje es un ejemplo ficticio."
        ),
    },
)


def _key(row: PlantillaRecord) -> tuple[str, str, str, int]:
    return (row.clave, row.canal, row.idioma, row.version)


async def seed_plantillas(
    store: PlantillaStore, *, tenant_id: uuid.UUID, idioma: str = "es"
) -> int:
    """Add missing approved templates for one tenant. Returns rows added."""
    existing = {_key(row) for row in await store.list_plantillas(tenant_id)}
    added = 0
    for data in PLANTILLAS_C11:
        candidate = PlantillaRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            clave=data["clave"],
            canal=data["canal"],
            idioma=idioma,
            version=1,
            cuerpo=data["cuerpo"],
            meta_template_name=data.get("meta_template_name"),
            activo=True,
        )
        if _key(candidate) in existing:
            continue
        await store.add(candidate)
        existing.add(_key(candidate))
        added += 1
    return added


async def seed_plantillas_session(session: Any, tenant_id: uuid.UUID) -> int:
    """SQLAlchemy session wrapper for production/CLI seeding."""
    from app.application.notificaciones import DbPlantillaStore

    return await seed_plantillas(
        DbPlantillaStore(session, tenant_id), tenant_id=tenant_id
    )


async def main() -> None:
    """CLI: ``python -m app.infrastructure.seed_c11`` from backend/."""
    import os

    from app.shared.db import create_engine_from_settings, create_session_factory

    tenant_id = uuid.UUID(os.environ["TENANT_ID"])
    engine = create_engine_from_settings()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            from sqlalchemy import text

            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            added = await seed_plantillas_session(session, tenant_id)
            await session.commit()
            print({"plantillas_agregadas": added})
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
