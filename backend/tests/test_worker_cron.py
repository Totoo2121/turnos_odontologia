"""Worker cron releases unconfirmed slots (C-08 task 2.1)."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


from datetime import datetime, timedelta, timezone

import app.api.turnero_publico as tp
from app.worker.tasks import liberar_huecos_sin_confirmacion


def test_liberar_huecos_cancela_reservados_vencidos() -> None:
    tp._PORTAL.clear()
    now = datetime.now(timezone.utc)
    expired_token = "expired-token"
    tp._PORTAL[expired_token] = {
        "token": expired_token,
        "estado": "reservado",
        "inicio": now - timedelta(hours=2),
        "anticipacion_min_cancel_hs": 24,
        "umbral_confirmacion_hs": 1,
    }
    fresh_token = "fresh-token"
    tp._PORTAL[fresh_token] = {
        "token": fresh_token,
        "estado": "reservado",
        "inicio": now + timedelta(hours=48),
        "anticipacion_min_cancel_hs": 24,
        "umbral_confirmacion_hs": 1,
    }

    liberar_huecos_sin_confirmacion(umbral_hs=1)

    assert tp._PORTAL[expired_token]["estado"] == "cancelado"
    assert tp._PORTAL[fresh_token]["estado"] == "reservado"