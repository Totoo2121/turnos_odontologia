"""FastAPI application factory."""

from fastapi import FastAPI

from app.api.auth import configure_rate_limiting
from app.api.auth import router as auth_router
from app.api.catalog import router as catalog_router
from app.api.health import router as health_router
from app.shared.exceptions import register_exception_handlers
from app.shared.logging import get_logger

log = get_logger(__name__)


def create_app() -> FastAPI:
    """Build the FastAPI app (settings validated eagerly for fail-fast)."""
    from app.shared.settings import get_settings

    get_settings()
    app = FastAPI(title="Turnos Odontología API")
    configure_rate_limiting(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(catalog_router, prefix="/api")
    register_exception_handlers(app)
    log.info("app created")
    return app


app = create_app()
