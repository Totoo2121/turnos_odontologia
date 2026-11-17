"""Shared C-11 runtime (in-memory scaffold, same staged pattern as C-09/C-10).

The authenticated API uses DB-backed stores; the public webhook and the
worker share this in-memory registry so both can run without a live
multi-tenant session. Wiring the worker to the DB stores is a deployment
concern tracked with the rest of the C-09/C-10 scaffolds.
"""

from __future__ import annotations

from app.application.notificaciones import (
    MemoryPlantillaStore,
    MemoryRecordatorioStore,
    MemoryTurnoNotificacionStore,
    NotificacionService,
)
from app.infrastructure.smtp import EmailClient, build_email_client
from app.infrastructure.whatsapp_bsp import (
    MetaCloudWhatsAppClient,
    WhatsAppClient,
)
from app.shared.settings import get_settings

PLANTILLAS = MemoryPlantillaStore()
RECORDATORIOS = MemoryRecordatorioStore()
TURNOS = MemoryTurnoNotificacionStore()

_defaults_ready = False


def build_whatsapp_client() -> WhatsAppClient:
    settings = get_settings()
    # Sin credenciales el adaptador falla de forma permanente y el servicio
    # cae a email/alerta interna (RN-NO-05: jamás un canal no oficial).
    return MetaCloudWhatsAppClient(
        token=settings.wa_bsp_token, phone_id=settings.wa_phone_id
    )


def build_service(
    whatsapp: WhatsAppClient | None = None,
    email: EmailClient | None = None,
) -> NotificacionService:
    settings = get_settings()
    return NotificacionService(
        recordatorios=RECORDATORIOS,
        plantillas=PLANTILLAS,
        whatsapp=whatsapp if whatsapp is not None else build_whatsapp_client(),
        email=email if email is not None else build_email_client(settings),
        max_intentos=settings.notif_max_intentos,
        backoff_base_s=settings.notif_backoff_base_s,
    )


SERVICE = build_service()


async def ensure_default_templates() -> None:
    """Seed platform-provided templates once (global fallback scope)."""
    global _defaults_ready
    if _defaults_ready:
        return
    from app.application.notificaciones import PLANTILLA_GLOBAL_TENANT
    from app.infrastructure.seed_c11 import seed_plantillas

    await seed_plantillas(PLANTILLAS, tenant_id=PLANTILLA_GLOBAL_TENANT)
    _defaults_ready = True


def reset_runtime() -> None:
    """Test helper: clear shared state and re-arm default template seeding."""
    global _defaults_ready
    PLANTILLAS.clear()
    RECORDATORIOS.clear()
    TURNOS.reset()
    _defaults_ready = False
