"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agenda_cobros import router as agenda_cobros_router
from app.api.admin import router as admin_router
from app.api.audit import record_api_event, record_tenant_event
from app.api.etapa2 import router as etapa2_router
from app.api.auth import configure_rate_limiting
from app.api.auth import router as auth_router
from app.api.caja import router as caja_router
from app.api.catalog import router as catalog_router
from app.api.clinica import router as clinica_router, storage_router as clinica_storage_router
from app.api.cobros_webhook import router as cobros_webhook_router
from app.api.health import router as health_router
from app.api.lista_espera import router as lista_espera_router
from app.api.notificaciones import router as notificaciones_router
from app.api.pacientes import router as pacientes_router
from app.api.presupuestos import router as presupuestos_router
from app.api.reportes import router as reportes_router
from app.api.turnero_publico import router as turnero_router
from app.api.turnos import router as turnos_router
from app.api.whatsapp_webhook import router as whatsapp_webhook_router
from app.shared.exceptions import register_exception_handlers
from app.shared.logging import get_logger

log = get_logger(__name__)


def create_app() -> FastAPI:
    """Build the FastAPI app (settings validated eagerly for fail-fast)."""
    from app.shared.settings import get_settings

    settings = get_settings()
    app = FastAPI(title="Turnos Odontología API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.audit_recorder = record_api_event
    app.state.audit_webhook_recorder = record_tenant_event
    configure_rate_limiting(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(catalog_router, prefix="/api")
    app.include_router(lista_espera_router, prefix="/api")
    app.include_router(agenda_cobros_router, prefix="/api")
    app.include_router(turnos_router, prefix="/api")
    app.include_router(notificaciones_router, prefix="/api")
    app.include_router(pacientes_router, prefix="/api")
    app.include_router(clinica_router, prefix="/api")
    app.include_router(clinica_storage_router, prefix="/api")
    app.include_router(presupuestos_router, prefix="/api")
    app.include_router(reportes_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(etapa2_router, prefix="/api")
    app.include_router(caja_router, prefix="/api")
    app.include_router(turnero_router)
    app.include_router(cobros_webhook_router, prefix="/api")
    app.include_router(whatsapp_webhook_router)
    register_exception_handlers(app)
    log.info("app created")
    return app


app = create_app()
