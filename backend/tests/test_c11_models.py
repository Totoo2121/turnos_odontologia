"""C-11 task 1.1/1.2: model columns and tenant metadata (RED first)."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from app.domain.agenda.models import Prestacion, Turno
from app.domain.notificaciones.models import PlantillaMensaje, Recordatorio
from app.shared.db import metadata


def test_turno_has_c11_contact_and_confirmation_columns() -> None:
    """WHEN Turno inspected THEN contact snapshot + confirmado_at exist."""
    columns = set(Turno.__table__.columns.keys())
    assert {"contacto_whatsapp", "contacto_email", "confirmado_at"} <= columns
    assert Turno.__table__.columns["contacto_whatsapp"].nullable is True
    assert Turno.__table__.columns["contacto_email"].nullable is True
    assert Turno.__table__.columns["confirmado_at"].nullable is True


def test_prestacion_has_control_interval() -> None:
    """WHEN Prestacion inspected THEN intervalo_control_dias is nullable."""
    column = Prestacion.__table__.columns["intervalo_control_dias"]
    assert column.nullable is True


def test_plantilla_table_shape() -> None:
    """WHEN PlantillaMensaje inspected THEN tenant + version + channel checks."""
    table = PlantillaMensaje.__table__
    assert table.name == "plantilla_mensaje"
    assert {"tenant_id", "clave", "canal", "idioma", "version", "cuerpo"} <= set(
        table.columns.keys()
    )
    constraints = {c.name for c in table.constraints}
    assert "uq_plantilla_mensaje_version" in constraints
    assert any(name.endswith("plantilla_canal_enum") for name in constraints)
    assert any(name.endswith("plantilla_version_pos") for name in constraints)


def test_recordatorio_table_shape() -> None:
    """WHEN Recordatorio inspected THEN delivery state + unique idempotency key."""
    table = Recordatorio.__table__
    assert table.name == "recordatorio"
    assert {
        "tenant_id",
        "turno_id",
        "canal",
        "tipo",
        "plantilla",
        "enviar_at",
        "estado",
        "intentos",
        "confirmado_at",
    } <= set(table.columns.keys())
    constraints = {c.name for c in table.constraints}
    assert "uq_recordatorio_turno_canal_tipo" in constraints
    assert any(name.endswith("recordatorio_canal_enum") for name in constraints)
    assert any(name.endswith("recordatorio_tipo_enum") for name in constraints)
    assert any(name.endswith("recordatorio_estado_enum") for name in constraints)


def test_models_registered_on_shared_metadata() -> None:
    """WHEN metadata inspected THEN C-11 tables are visible to Alembic."""
    assert "plantilla_mensaje" in metadata.tables
    assert "recordatorio" in metadata.tables
