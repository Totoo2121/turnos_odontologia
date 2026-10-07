"""Celery scaffold (no real tasks, no beat — seams for C-09/C-11)."""

import os

from celery import Celery  # type: ignore[import-untyped]

celery_app = Celery(
    "turnos",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={},
)
