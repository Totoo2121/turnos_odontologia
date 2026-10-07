"""C-05 catalog schemas tests (task 2.1) — RED first.

Pure Pydantic v2 validation: 422-shaped ValidationErrors for business-rule
violations, happy paths for valid payloads. No DB needed.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.api.catalog_schemas import (
    BloqueoCreate,
    BloqueoUpdate,
    PrestacionCreate,
    PrestacionUpdate,
    ProfesionalCreate,
    ProfesionalUpdate,
    SillonCreate,
    SillonUpdate,
)


def test_prestacion_valida_pasa() -> None:
    """WHEN Limpieza 45'+10 creada THEN el schema acepta todos los parametros."""
    payload = PrestacionCreate(
        nombre="Limpieza (ficticia)",
        duracion_min=45,
        buffer_min=10,
        precio="15000.00",
        anticipacion_min_cancel_hs=24,
    )
    assert payload.duracion_min == 45
    assert payload.buffer_min == 10


def test_prestacion_duracion_no_positiva_rechazada() -> None:
    """WHEN duracion<=0 THEN ValidationError (nada persiste)."""
    with pytest.raises(ValidationError):
        PrestacionCreate(nombre="X (ficticia)", duracion_min=0)
    with pytest.raises(ValidationError):
        PrestacionCreate(nombre="X (ficticia)", duracion_min=-30)


def test_prestacion_update_duracion_no_positiva_rechazada() -> None:
    """WHEN update con duracion<=0 THEN ValidationError (2do input: update)."""
    with pytest.raises(ValidationError):
        PrestacionUpdate(duracion_min=0)


def test_prestacion_buffer_negativo_rechazado() -> None:
    """WHEN buffer<0 THEN ValidationError."""
    with pytest.raises(ValidationError):
        PrestacionCreate(nombre="X (ficticia)", duracion_min=30, buffer_min=-5)


def test_sena_obligatoria_exige_monto() -> None:
    """WHEN seña obligatoria sin monto THEN ValidationError con monto faltante."""
    with pytest.raises(ValidationError, match="monto"):
        PrestacionCreate(
            nombre="Corona (ficticia)",
            duracion_min=60,
            sena_obligatoria=True,
        )


def test_sena_obligatoria_monto_no_positivo_rechazado() -> None:
    """WHEN seña obligatoria con monto<=0 THEN ValidationError (triangula)."""
    with pytest.raises(ValidationError):
        PrestacionCreate(
            nombre="Corona (ficticia)",
            duracion_min=60,
            sena_obligatoria=True,
            monto_sena="0.00",
        )
    with pytest.raises(ValidationError):
        PrestacionUpdate(sena_obligatoria=True, monto_sena="-100.00")


def test_sena_opcional_sin_monto_pasa() -> None:
    """WHEN seña no obligatoria sin monto THEN el schema acepta."""
    payload = PrestacionCreate(nombre="Consulta (ficticia)", duracion_min=30)
    assert payload.sena_obligatoria is False
    assert payload.monto_sena is None


def test_profesional_sin_prestaciones_no_agendable() -> None:
    """WHEN profesional sin habilitaciones THEN 422 (ValidationError)."""
    with pytest.raises(ValidationError):
        ProfesionalCreate(nombre="Dra. Demo (ficticia)", prestacion_ids=[])
    with pytest.raises(ValidationError):
        ProfesionalUpdate(prestacion_ids=[])


def test_profesional_con_habilitaciones_pasa() -> None:
    """WHEN profesional con 2 prestaciones THEN 201-shape valido."""
    payload = ProfesionalCreate(
        nombre="Dr. Demo (ficticio)",
        especialidades=["Ortodoncia (ficticia)"],
        prestacion_ids=[uuid.uuid4(), uuid.uuid4()],
    )
    assert len(payload.prestacion_ids) == 2


def test_bloqueo_sin_objetivo_rechazado() -> None:
    """WHEN bloqueo sin profesional ni sillon THEN ValidationError."""
    inicio = datetime.now(UTC) + timedelta(days=30)
    with pytest.raises(ValidationError, match="objetivo"):
        BloqueoCreate(inicio=inicio, fin=inicio + timedelta(hours=8), motivo="feriado")


def test_bloqueo_fin_antes_de_inicio_rechazado() -> None:
    """WHEN fin<=inicio THEN ValidationError (igual y anterior: triangula)."""
    inicio = datetime.now(UTC) + timedelta(days=30)
    with pytest.raises(ValidationError):
        BloqueoCreate(
            inicio=inicio,
            fin=inicio,
            motivo="licencia",
            profesional_id=uuid.uuid4(),
        )
    with pytest.raises(ValidationError):
        BloqueoUpdate(inicio=inicio, fin=inicio - timedelta(hours=1))


def test_bloqueo_con_un_objetivo_pasa() -> None:
    """WHEN bloqueo con solo sillon THEN valido (un objetivo basta)."""
    inicio = datetime.now(UTC) + timedelta(days=30)
    payload = BloqueoCreate(
        inicio=inicio,
        fin=inicio + timedelta(hours=8),
        motivo="feriado",
        sillon_id=uuid.uuid4(),
    )
    assert payload.motivo == "feriado"


def test_bloqueo_motivo_fuera_de_enum_rechazado() -> None:
    """WHEN motivo desconocido THEN ValidationError."""
    inicio = datetime.now(UTC) + timedelta(days=30)
    with pytest.raises(ValidationError):
        BloqueoCreate(
            inicio=inicio,
            fin=inicio + timedelta(hours=1),
            motivo="fiesta-ficticia",
            profesional_id=uuid.uuid4(),
        )


def test_precio_cero_aceptado_sin_sena() -> None:
    """WHEN precio=0 sin seña THEN valido (consulta gratuita ficticia)."""
    payload = PrestacionCreate(
        nombre="Consulta gratuita (ficticia)", duracion_min=30, precio="0.00"
    )
    assert payload.precio == 0


def test_sillon_requiere_nombre() -> None:
    """WHEN sillon sin nombre THEN ValidationError; con nombre pasa."""
    with pytest.raises(ValidationError):
        SillonCreate(nombre="  ")
    assert SillonCreate(nombre="Box 1 (demo)").activo is True
    assert SillonUpdate(activo=False).activo is False
