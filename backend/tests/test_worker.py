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


def test_celery_scaffold_has_no_beat_and_no_real_tasks() -> None:
    """WHEN worker app inspected THEN no beat schedule and no domain tasks."""
    from app.worker.celery_app import celery_app

    assert not celery_app.conf.beat_schedule
    registered = set(celery_app.tasks.keys())
    assert not any(k.startswith("app.domain") for k in registered)
