"""Celery scaffold tests (C-01 task 2.4) — app object only, no broker needed."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def test_celery_app_uses_redis_broker() -> None:
    """WHEN worker app inspected THEN broker is Redis (no connection opened)."""
    from app.worker.celery_app import celery_app

    assert "redis" in celery_app.conf.broker_url


def test_celery_app_registers_c10_vencimiento_job() -> None:
    """WHEN worker app inspected THEN C-10 job is registered and scheduled."""
    import app.worker.tasks  # noqa: F401  (registra el task en Celery)
    from app.worker.celery_app import celery_app

    assert "app.worker.tasks.vencer_ordenes_sin_acreditar" in celery_app.tasks
    assert "c10-vencer-ordenes-sin-acreditar" in celery_app.conf.beat_schedule
