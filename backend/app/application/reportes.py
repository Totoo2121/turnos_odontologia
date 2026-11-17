"""Tenant-scoped read models for C-16 operational and cash reports."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agenda_cobros import AGENDA_TZ
from app.domain.agenda.models import Pago, Profesional, Turno
from app.domain.clinica.models import CuentaCorriente, MovimientoCC
from app.shared.exceptions import AppError


def bounds(desde: date, hasta: date) -> tuple[datetime, datetime]:
    if hasta < desde or (hasta - desde).days > 366:
        raise AppError("rango inválido (máximo 367 días)", 422)
    return (
        datetime.combine(desde, time.min, AGENDA_TZ),
        datetime.combine(hasta + timedelta(days=1), time.min, AGENDA_TZ),
    )


def tasa_ausentismo(ausentes: int, turnos: int) -> float:
    """Share of missed appointments, with an explicit empty-period zero."""
    return round(ausentes / turnos * 100, 2) if turnos else 0.0


async def report_scope(
    session: AsyncSession, tenant_id: uuid.UUID, roles: tuple[str, ...], subject: str
) -> tuple[str, uuid.UUID | None]:
    if "propietario" in roles:
        return "total", None
    if "odontologo" in roles:
        try:
            user_id = uuid.UUID(subject)
        except ValueError:
            raise AppError("profesional no configurado", 403) from None
        profesional_id = await session.scalar(
            select(Profesional.id).where(
                Profesional.tenant_id == tenant_id,
                Profesional.usuario_id == user_id,
            )
        )
        if profesional_id is None:
            raise AppError("profesional no configurado", 403)
        return "propio", profesional_id
    if any(role in roles for role in ("recepcion", "asistente")):
        return "operativo", None
    raise AppError("forbidden", 403)


def _scope(stmt: Any, professional_id: uuid.UUID | None) -> Any:
    return stmt if professional_id is None else stmt.where(Profesional.id == professional_id)


async def ocupacion(
    session: AsyncSession, tenant_id: uuid.UUID, desde: date, hasta: date,
    professional_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    start, end = bounds(desde, hasta)
    minutes = func.extract("epoch", Turno.fin - Turno.inicio) / 60
    stmt = select(
        Profesional.id.label("profesional_id"),
        Profesional.nombre.label("profesional"),
        func.count(case((Turno.estado != "cancelado", 1))).label("turnos"),
        func.coalesce(func.sum(case((Turno.estado != "cancelado", minutes), else_=0)), 0).label("minutos_ocupados"),
        func.count(case((Turno.estado == "atendido", 1))).label("atendidos"),
        func.count(case((Turno.estado == "ausente", 1))).label("ausentes"),
        func.count(case((Turno.estado == "cancelado", 1))).label("cancelados"),
    ).select_from(Profesional).outerjoin(
        Turno,
        (Turno.profesional_id == Profesional.id)
        & (Turno.tenant_id == tenant_id)
        & (Turno.inicio >= start)
        & (Turno.inicio < end)
    ).where(Profesional.tenant_id == tenant_id)
    stmt = _scope(stmt, professional_id).group_by(Profesional.id, Profesional.nombre).order_by(Profesional.nombre)
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "profesional_id": str(row["profesional_id"]),
            "profesional": row["profesional"],
            "turnos": int(row["turnos"]),
            "minutos_ocupados": int(row["minutos_ocupados"]),
            "atendidos": int(row["atendidos"]),
            "ausentes": int(row["ausentes"]),
            "cancelados": int(row["cancelados"]),
        }
        for row in rows
    ]


async def ausentismo(
    session: AsyncSession, tenant_id: uuid.UUID, desde: date, hasta: date,
    professional_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    start, end = bounds(desde, hasta)
    stmt = select(
        Profesional.id.label("profesional_id"),
        Profesional.nombre.label("profesional"),
        func.count(Turno.id).label("turnos"),
        func.count(case((Turno.estado == "ausente", 1))).label("ausentes"),
        func.count(case((Turno.estado == "cancelado", 1))).label("cancelados"),
    ).select_from(Profesional).outerjoin(
        Turno,
        (Turno.profesional_id == Profesional.id)
        & (Turno.tenant_id == tenant_id)
        & (Turno.inicio >= start)
        & (Turno.inicio < end),
    ).where(Profesional.tenant_id == tenant_id)
    stmt = _scope(stmt, professional_id).group_by(Profesional.id, Profesional.nombre).order_by(Profesional.nombre)
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "profesional_id": str(row["profesional_id"]),
            "profesional": row["profesional"],
            "turnos": int(row["turnos"]),
            "ausentes": int(row["ausentes"]),
            "cancelados": int(row["cancelados"]),
            "tasa_ausentismo": tasa_ausentismo(int(row["ausentes"]), int(row["turnos"])),
        }
        for row in rows
    ]


async def recaudacion(
    session: AsyncSession, tenant_id: uuid.UUID, desde: date, hasta: date,
    professional_id: uuid.UUID | None,
) -> dict[str, Any]:
    start, end = bounds(desde, hasta)
    credited = await session.execute(
        select(
            Profesional.id.label("profesional_id"),
            Profesional.nombre.label("profesional"),
            func.coalesce(func.sum(Pago.monto), 0).label("senias_acreditadas"),
            func.count(Pago.id).label("cantidad_senias"),
        ).select_from(Profesional).join(
            Turno, (Turno.profesional_id == Profesional.id) & (Turno.tenant_id == tenant_id)
        ).join(Pago, (Pago.turno_id == Turno.id) & (Pago.tenant_id == tenant_id))
        .where(
            Profesional.tenant_id == tenant_id,
            Pago.estado == "acreditado",
            Pago.acreditado_at >= start,
            Pago.acreditado_at < end,
            *([Profesional.id == professional_id] if professional_id else []),
        ).group_by(Profesional.id, Profesional.nombre).order_by(Profesional.nombre)
    )
    by_professional = [
        {"profesional_id": str(row.profesional_id), "profesional": row.profesional,
         "senias_acreditadas": str(row.senias_acreditadas), "cantidad_senias": int(row.cantidad_senias)}
        for row in credited
    ]
    manual = await session.execute(
        select(
            func.coalesce(func.sum(MovimientoCC.monto), 0),
            func.count(MovimientoCC.id),
        ).where(
            MovimientoCC.tenant_id == tenant_id,
            MovimientoCC.tipo == "credito",
            MovimientoCC.ocurrido_at >= start,
            MovimientoCC.ocurrido_at < end,
        )
    )
    manual_total, manual_count = manual.one()
    pending = await session.execute(
        select(
            func.coalesce(func.sum(MovimientoCC.monto), 0),
        ).where(
            MovimientoCC.tenant_id == tenant_id,
            MovimientoCC.tipo == "debito",
        )
    )
    debits = Decimal(pending.scalar_one())
    credits = Decimal((await session.execute(
        select(func.coalesce(func.sum(MovimientoCC.monto), 0)).where(
            MovimientoCC.tenant_id == tenant_id,
            MovimientoCC.tipo == "credito",
        )
    )).scalar_one())
    if professional_id is not None:
        # Account payments and plan balances are not attributed to an individual
        # clinician in the ledger; never leak tenant-wide financial values.
        manual_total, manual_count = Decimal(0), 0
        debits, credits = Decimal(0), Decimal(0)
    return {
        "senias_acreditadas": str(sum((Decimal(row["senias_acreditadas"]) for row in by_professional), Decimal(0))),
        "cobros_cuenta_corriente": str(manual_total),
        "total_cobrado": str(sum((Decimal(row["senias_acreditadas"]) for row in by_professional), Decimal(0)) + Decimal(manual_total)),
        "cantidad_cobros_cuenta_corriente": int(manual_count),
        "deuda_neta_planes": str(max(debits - credits, Decimal(0))),
        "por_profesional": by_professional,
    }


async def senias_pendientes(
    session: AsyncSession, tenant_id: uuid.UUID, desde: date, hasta: date,
    professional_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    start, end = bounds(desde, hasta)
    stmt = select(
        Pago.id.label("pago_id"), Turno.id.label("turno_id"),
        Profesional.nombre.label("profesional"), Pago.monto, Pago.moneda,
        Pago.created_at,
    ).select_from(Pago).join(
        Turno, (Turno.id == Pago.turno_id) & (Turno.tenant_id == tenant_id)
    ).join(
        Profesional, (Profesional.id == Turno.profesional_id)
        & (Profesional.tenant_id == tenant_id)
    ).where(
        Pago.tenant_id == tenant_id, Pago.estado == "pendiente",
        Pago.created_at >= start, Pago.created_at < end,
        *([Profesional.id == professional_id] if professional_id else []),
    ).order_by(Pago.created_at)
    rows = (await session.execute(stmt)).mappings().all()
    return [{
        "pago_id": str(row["pago_id"]), "turno_id": str(row["turno_id"]),
        "profesional": row["profesional"], "monto": str(row["monto"]),
        "moneda": row["moneda"], "created_at": row["created_at"].isoformat(),
    } for row in rows]
