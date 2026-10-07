"""C-05 catalog Pydantic v2 schemas (D5): validation at the edge, DB last.

Strict shapes: ``extra="forbid"`` everywhere, non-blank names, ``duracion >
0``, ``buffer >= 0``, bloqueo with at least one target and ``fin > inicio``,
and the deposit rule (``sena_obligatoria → monto_sena > 0``). Mirror CHECKs
live in migration 003 so the DB rejects whatever slips past the edge.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MotivoBloqueo = Literal["feriado", "licencia", "administrativo", "mantenimiento"]

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _monto_positivo(value: Decimal | None, *, field: str) -> Decimal | None:
    if value is not None and value <= 0:
        raise ValueError(f"{field} debe ser positivo")
    return value


class PrestacionCreate(BaseModel):
    """Create body for a prestacion (all scheduling rules included)."""

    model_config = _STRICT

    nombre: str = Field(min_length=1, max_length=160)
    duracion_min: int = Field(gt=0)
    buffer_min: int = Field(default=0, ge=0)
    requiere_sillon: bool = True
    permite_sobreturno: bool = False
    sena_obligatoria: bool = False
    monto_sena: Decimal | None = Field(default=None)
    anticipacion_min_cancel_hs: int = Field(default=24, ge=0)
    precio: Decimal | None = Field(default=None, ge=0)

    _monto = field_validator("monto_sena")(  # type: ignore[misc]
        lambda cls, v: _monto_positivo(v, field="monto")
    )

    @model_validator(mode="after")
    def _sena_exige_monto(self) -> PrestacionCreate:
        if self.sena_obligatoria and (
            self.monto_sena is None or self.monto_sena <= 0
        ):
            raise ValueError("monto_sena positivo es obligatorio con sena_obligatoria")
        return self


class PrestacionUpdate(BaseModel):
    """Patch body: every field optional, same business rules when present."""

    model_config = _STRICT

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    duracion_min: int | None = Field(default=None, gt=0)
    buffer_min: int | None = Field(default=None, ge=0)
    requiere_sillon: bool | None = None
    permite_sobreturno: bool | None = None
    sena_obligatoria: bool | None = None
    monto_sena: Decimal | None = Field(default=None)
    anticipacion_min_cancel_hs: int | None = Field(default=None, ge=0)
    precio: Decimal | None = Field(default=None, ge=0)

    _monto = field_validator("monto_sena")(  # type: ignore[misc]
        lambda cls, v: _monto_positivo(v, field="monto")
    )

    @model_validator(mode="after")
    def _sena_exige_monto(self) -> PrestacionUpdate:
        if self.sena_obligatoria and (
            self.monto_sena is None or self.monto_sena <= 0
        ):
            raise ValueError("monto_sena positivo es obligatorio con sena_obligatoria")
        return self


class PrestacionRead(BaseModel):
    """Read shape: persisted parameters plus lifecycle flag."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    duracion_min: int
    buffer_min: int
    requiere_sillon: bool
    permite_sobreturno: bool
    sena_obligatoria: bool
    monto_sena: Decimal | None
    anticipacion_min_cancel_hs: int
    precio: Decimal | None
    is_active: bool


class ProfesionalCreate(BaseModel):
    """Create body: at least one enabled prestacion to be schedulable."""

    model_config = _STRICT

    nombre: str = Field(min_length=1, max_length=160)
    matricula: str | None = Field(default=None, max_length=60)
    especialidades: list[str] = Field(default_factory=list)
    duracion_default_min: int = Field(default=30, gt=0)
    prestacion_ids: list[uuid.UUID] = Field(min_length=1)
    activo: bool = True


class ProfesionalUpdate(BaseModel):
    """Patch body: prestacion_ids present → must stay non-empty."""

    model_config = _STRICT

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    matricula: str | None = Field(default=None, max_length=60)
    especialidades: list[str] | None = None
    duracion_default_min: int | None = Field(default=None, gt=0)
    prestacion_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    activo: bool | None = None


class ProfesionalRead(BaseModel):
    """Read shape with enabled prestaciones."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    matricula: str | None
    especialidades: list[str]
    duracion_default_min: int
    prestacion_ids: list[uuid.UUID] = Field(default_factory=list)
    activo: bool
    is_active: bool


class SillonCreate(BaseModel):
    """Create body for a sillón/box resource."""

    model_config = _STRICT

    nombre: str = Field(min_length=1, max_length=160)
    sucursal_id: uuid.UUID | None = None
    activo: bool = True


class SillonUpdate(BaseModel):
    """Patch body for a sillón."""

    model_config = _STRICT

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    sucursal_id: uuid.UUID | None = None
    activo: bool | None = None


class SillonRead(BaseModel):
    """Read shape for a sillón."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    sucursal_id: uuid.UUID | None
    activo: bool
    is_active: bool


class BloqueoCreate(BaseModel):
    """Create body: at least one target, fin > inicio, closed motivo enum."""

    model_config = _STRICT

    profesional_id: uuid.UUID | None = None
    sillon_id: uuid.UUID | None = None
    inicio: datetime
    fin: datetime
    motivo: MotivoBloqueo

    @model_validator(mode="after")
    def _reglas(self) -> BloqueoCreate:
        if self.profesional_id is None and self.sillon_id is None:
            raise ValueError("el bloqueo debe apuntar a al menos un objetivo")
        if self.fin <= self.inicio:
            raise ValueError("fin debe ser posterior a inicio")
        return self


class BloqueoUpdate(BaseModel):
    """Patch body: same rules applied to the resulting (inicio, fin)."""

    model_config = _STRICT

    profesional_id: uuid.UUID | None = None
    sillon_id: uuid.UUID | None = None
    inicio: datetime | None = None
    fin: datetime | None = None
    motivo: MotivoBloqueo | None = None

    @model_validator(mode="after")
    def _reglas(self) -> BloqueoUpdate:
        if self.inicio is not None and self.fin is not None and self.fin <= self.inicio:
            raise ValueError("fin debe ser posterior a inicio")
        return self


class BloqueoRead(BaseModel):
    """Read shape for a bloqueo."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profesional_id: uuid.UUID | None
    sillon_id: uuid.UUID | None
    inicio: datetime
    fin: datetime
    motivo: str
    is_active: bool
