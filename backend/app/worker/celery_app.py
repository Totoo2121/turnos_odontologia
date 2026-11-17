"""Celery worker app: broker, acks and periodic beat entries (C-01/C-10)."""

import os

from celery import Celery  # type: ignore[import-untyped]

celery_app = Celery(
    "turnos",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # C-10 task 4.1: vence órdenes MP sin acreditar cada 15 min y libera hueco.
        "c10-vencer-ordenes-sin-acreditar": {
            "task": "app.worker.tasks.vencer_ordenes_sin_acreditar",
            "schedule": 900.0,
        },
        # C-11: recordatorios T-48h/T-24h y avisos de no confirmación.
        "c11-recordatorios": {
            "task": "app.worker.tasks.enviar_recordatorios_programados",
            "schedule": 900.0,
        },
        "c11-avisos-sin-confirmacion": {
            "task": "app.worker.tasks.avisar_turnos_sin_confirmacion",
            "schedule": 900.0,
        },
        # C-11: recall de ausentes y controles periódicos (cada 6 h).
        "c11-recall-ausentes": {
            "task": "app.worker.tasks.enviar_recalls_ausentes",
            "schedule": 21600.0,
        },
        "c11-recall-control": {
            "task": "app.worker.tasks.enviar_recalls_control",
            "schedule": 21600.0,
        },
    },
)
