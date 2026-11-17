"""C-08 worker tasks: auto-liberation of unconfirmed slots."""

from __future__ import annotations

import asyncio
import datetime
import os
import uuid

from app.api import turnero_publico as tp
from app.application.cobros import CobroService


def liberar_huecos_sin_confirmacion(umbral_hs: int = 1) -> int:
    """Cancel `reservado` turnos not confirmed within `umbral_hs` hours.

    Returns number of released slots.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    released = 0
    for rec in list(tp._PORTAL.values()):
        if rec.get("estado") != "reservado":
            continue
        inicio = rec["inicio"]
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=datetime.timezone.utc)
        umbral = rec.get("umbral_confirmacion_hs", umbral_hs)
        if inicio - now <= datetime.timedelta(hours=umbral):
            # vencido: dentro del umbral de confirmacion o ya pasado
            rec["estado"] = "cancelado"
            released += 1
    return released


# Celery registration (best-effort; broker may be unavailable in tests).
try:
    from app.worker.celery_app import celery_app

    @celery_app.task(name="app.worker.tasks.liberar_huecos_sin_confirmacion")
    def _celery_task(umbral_hs: int = 1) -> int:
        return liberar_huecos_sin_confirmacion(umbral_hs=umbral_hs)

except Exception:  # pragma: no cover
    pass


# C-17: full tenant export and deterministic deletion after its download window.
def generar_exportacion_job(exportacion_id: str, tenant_id: str) -> None:
    from app.application.exportacion import generar_exportacion

    asyncio.run(generar_exportacion(uuid.UUID(exportacion_id), uuid.UUID(tenant_id)))


def limpiar_exportacion_job(tenant_id: str, exportacion_id: str) -> bool:
    from app.application.exportacion import limpiar_exportacion

    return asyncio.run(limpiar_exportacion(uuid.UUID(tenant_id), uuid.UUID(exportacion_id)))


try:
    from app.worker.celery_app import celery_app as _c17_celery

    generar_exportacion_job = _c17_celery.task(
        name="app.worker.tasks.generar_exportacion"
    )(generar_exportacion_job)
    limpiar_exportacion_job = _c17_celery.task(
        name="app.worker.tasks.limpiar_exportacion"
    )(limpiar_exportacion_job)
except Exception:  # pragma: no cover
    pass


# C-10 task 4.1: worker periódico — vence órdenes sin acreditar y libera hueco
# (RN-AD-04).
PLAZO_COBROS_HS_POR_DEFECTO = 24


async def vencer_ordenes_sin_acreditar(
    *,
    plazo_hs: int = PLAZO_COBROS_HS_POR_DEFECTO,
    ahora: datetime.datetime | None = None,
    service: CobroService | None = None,
) -> int:
    """C-10 task 4.1: vence órdenes sin acreditar tras el plazo y libera el hueco.

    Worker periódico (Celery beat / próxima integración): itera los cobros en
    estado ``pendiente`` cuya orden superó el plazo configurable (default 24h) sin
    acreditación, y las vence (RN-AD-04 por encima de RN-TU-04 / RN-G-02).

    Returns the number of vencidas processed.
    """
    svc = service if service is not None else CobroService()
    now = ahora if ahora is not None else datetime.datetime.now(datetime.timezone.utc)
    plazo = datetime.timedelta(hours=plazo_hs)
    vencidas = 0
    for pago in await svc.pendientes():
        creada = pago.created_at or now
        if creada.tzinfo is None:
            creada = creada.replace(tzinfo=datetime.timezone.utc)
        if now - creada < plazo:
            continue  # todavia dentro del plazo de cobro
        await svc.anular(
            turno_id=pago.turno_id,
            tenant_id=pago.tenant_id,
            mp_payment_id=pago.mp_payment_id,
            monto=pago.monto,
            moneda=pago.moneda,
            motivo="vencido",
        )
        vencidas += 1
    return vencidas


def vencer_ordenes_sin_acreditar_job(
    plazo_hs: int | None = None,
    *,
    service: CobroService | None = None,
) -> int:
    """Entrypoint sync para Celery beat/task.

    Celery no awaitea coroutines: el job async se ejecuta con ``asyncio.run``.
    El plazo es configurable por env ``COBROS_PLAZO_HS`` (default 24h).
    """
    if plazo_hs is None:
        plazo_hs = int(os.getenv("COBROS_PLAZO_HS", PLAZO_COBROS_HS_POR_DEFECTO))
    return asyncio.run(vencer_ordenes_sin_acreditar(plazo_hs=plazo_hs, service=service))


# C-10 task 4.1: registro del job periódico en Celery (beat en celery_app.py).
try:
    from app.worker.celery_app import celery_app as _celery_app

    @_celery_app.task(name="app.worker.tasks.vencer_ordenes_sin_acreditar")
    def _celery_task_vencer_ordenes(plazo_hs: int | None = None) -> int:
        return vencer_ordenes_sin_acreditar_job(plazo_hs=plazo_hs)

except Exception:  # pragma: no cover
    pass


# C-09: oferta al liberar hueco (in-memory scaffold).
_LISTA_ESPERA = []


def ofertar_hueco_liberado(prestacion_id, franja, profesional_id=None, ventana_hs=2, ahora=None, registros=None):
    import datetime
    if ahora is None:
        ahora = datetime.datetime.now(datetime.timezone.utc)
    if registros is None:
        registros = _LISTA_ESPERA
    vencimiento = ahora + datetime.timedelta(hours=ventana_hs)
    compatibles = []
    for rec in registros:
        if rec.get('estado') != 'activa':
            continue
        if rec.get('prestacion_id') != prestacion_id:
            continue
        if rec.get('franja') != franja:
            continue
        rec_prof = rec.get('profesional_id')
        if rec_prof is not None and profesional_id is not None and rec_prof != profesional_id:
            continue
        compatibles.append(rec)
    if not compatibles:
        return 0
    compatibles.sort(key=lambda r: r.get('created_at', ahora))
    elegido = compatibles[0]
    elegido['estado'] = 'ofrecida'
    elegido['ofrecida_hasta'] = vencimiento
    return 1


ofrecer_hueco_liberado = ofertar_hueco_liberado
job_oferta_hueco = ofertar_hueco_liberado


def vencer_y_rotar_ofertas(prestacion_id=None, franja=None, profesional_id=None,
                            ventana_hs=2, ahora=None, registros=None):
    """Mark expired `ofrecida` entries as `vencida` and rotate offer to next compatible."""
    import datetime
    if ahora is None:
        ahora = datetime.datetime.now(datetime.timezone.utc)
    if registros is None:
        registros = _LISTA_ESPERA
    rotated = 0
    expired = []
    for rec in list(registros):
        if rec.get('estado') != 'ofrecida':
            continue
        if prestacion_id is not None and rec.get('prestacion_id') != prestacion_id:
            continue
        if franja is not None and rec.get('franja') != franja:
            continue
        hasta = rec.get('ofrecida_hasta')
        if hasta is None:
            continue
        if getattr(hasta, 'tzinfo', None) is None:
            hasta = hasta.replace(tzinfo=datetime.timezone.utc)
        if hasta <= ahora:
            expired.append(rec)
    for rec in expired:
        rec['estado'] = 'vencida'
        compatibles = []
        for r in registros:
            if r.get('estado') != 'activa':
                continue
            if r.get('prestacion_id') != rec.get('prestacion_id'):
                continue
            if r.get('franja') != rec.get('franja'):
                continue
            rec_prof = rec.get('profesional_id')
            r_prof = r.get('profesional_id')
            if rec_prof is not None and r_prof is not None and r_prof != rec_prof:
                continue
            compatibles.append(r)
        if compatibles:
            compatibles.sort(key=lambda r: r.get('created_at', ahora))
            nxt = compatibles[0]
            nxt['estado'] = 'ofrecida'
            nxt['ofrecida_hasta'] = ahora + datetime.timedelta(hours=ventana_hs)
            rotated += 1
    return rotated


# aliases
vencer_ofertas = vencer_y_rotar_ofertas
rotar_oferta_vencida = vencer_y_rotar_ofertas
vencer_ofertas_vencidas = vencer_y_rotar_ofertas
job_vencimiento = vencer_y_rotar_ofertas
job_rotacion = vencer_y_rotar_ofertas


# --- C-11 notification jobs -------------------------------------------------


def _notificacion_defaults() -> tuple[int, int, int, int]:
    from app.shared.settings import get_settings

    settings = get_settings()
    return (
        settings.reminder_t48h_hs,
        settings.reminder_t24h_hs,
        settings.confirmation_threshold_hs,
        settings.recall_ausente_dias,
    )


async def enviar_recordatorios_programados(
    *,
    ahora: datetime.datetime | None = None,
    service=None,
    turnos=None,
    t48h: int | None = None,
    t24h: int | None = None,
) -> int:
    """C-11: schedule/send T-48h/T-24h WhatsApp + email reminders (RN-NO-01)."""
    from app.application import notificaciones_runtime as runtime
    from app.application.notificaciones import programar_recordatorios

    d48, d24, _, _ = _notificacion_defaults()
    await runtime.ensure_default_templates()
    svc = service if service is not None else runtime.SERVICE
    store = turnos if turnos is not None else runtime.TURNOS
    return await programar_recordatorios(
        svc,
        store,
        ahora=ahora or datetime.datetime.now(datetime.UTC),
        t48h=t48h if t48h is not None else d48,
        t24h=t24h if t24h is not None else d24,
    )


async def avisar_turnos_sin_confirmacion(
    *,
    ahora: datetime.datetime | None = None,
    service=None,
    turnos=None,
    umbral_hs: int | None = None,
    on_hueco_riesgo=None,
) -> int:
    """C-11: reception alert + waitlist offer when confirmation threshold hits."""
    from app.application import notificaciones_runtime as runtime
    from app.application.notificaciones import avisar_sin_confirmacion

    _, _, umbral_default, _ = _notificacion_defaults()
    await runtime.ensure_default_templates()
    svc = service if service is not None else runtime.SERVICE
    store = turnos if turnos is not None else runtime.TURNOS

    if on_hueco_riesgo is None:

        async def _offer(turno):  # type: ignore[no-untyped-def]
            franja = "manana" if turno.inicio.hour < 12 else "tarde"
            ofertar_hueco_liberado(turno.prestacion_id, franja)

        on_hueco_riesgo = _offer

    return await avisar_sin_confirmacion(
        svc,
        store,
        ahora=ahora or datetime.datetime.now(datetime.UTC),
        umbral_hs=umbral_hs if umbral_hs is not None else umbral_default,
        on_hueco_riesgo=on_hueco_riesgo,
    )


async def enviar_recalls_ausentes(
    *,
    ahora: datetime.datetime | None = None,
    service=None,
    turnos=None,
    dias: int | None = None,
) -> int:
    """C-11: recall 7 days after an absence (RN-NO-03)."""
    from app.application import notificaciones_runtime as runtime
    from app.application.notificaciones import programar_recalls_ausentes

    _, _, _, dias_default = _notificacion_defaults()
    await runtime.ensure_default_templates()
    svc = service if service is not None else runtime.SERVICE
    store = turnos if turnos is not None else runtime.TURNOS
    return await programar_recalls_ausentes(
        svc,
        store,
        ahora=ahora or datetime.datetime.now(datetime.UTC),
        dias=dias if dias is not None else dias_default,
    )


async def enviar_recalls_control(
    *,
    ahora: datetime.datetime | None = None,
    service=None,
    turnos=None,
) -> int:
    """C-11: periodic follow-up recalls by prestacion interval (RN-NO-04)."""
    from app.application import notificaciones_runtime as runtime
    from app.application.notificaciones import programar_recalls_control

    await runtime.ensure_default_templates()
    svc = service if service is not None else runtime.SERVICE
    store = turnos if turnos is not None else runtime.TURNOS
    return await programar_recalls_control(
        svc,
        store,
        ahora=ahora or datetime.datetime.now(datetime.UTC),
    )


def _run_async(coro) -> int:  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def enviar_recordatorios_programados_job(
    t48h: int | None = None, t24h: int | None = None
) -> int:
    return _run_async(enviar_recordatorios_programados(t48h=t48h, t24h=t24h))


def avisar_turnos_sin_confirmacion_job(umbral_hs: int | None = None) -> int:
    return _run_async(avisar_turnos_sin_confirmacion(umbral_hs=umbral_hs))


def enviar_recalls_ausentes_job(dias: int | None = None) -> int:
    return _run_async(enviar_recalls_ausentes(dias=dias))


def enviar_recalls_control_job() -> int:
    return _run_async(enviar_recalls_control())


try:
    from app.worker.celery_app import celery_app as _celery_app_c11

    @_celery_app_c11.task(name="app.worker.tasks.enviar_recordatorios_programados")
    def _celery_c11_recordatorios(
        t48h: int | None = None, t24h: int | None = None
    ) -> int:
        return enviar_recordatorios_programados_job(t48h=t48h, t24h=t24h)

    @_celery_app_c11.task(name="app.worker.tasks.avisar_turnos_sin_confirmacion")
    def _celery_c11_avisos(umbral_hs: int | None = None) -> int:
        return avisar_turnos_sin_confirmacion_job(umbral_hs=umbral_hs)

    @_celery_app_c11.task(name="app.worker.tasks.enviar_recalls_ausentes")
    def _celery_c11_recall_ausentes(dias: int | None = None) -> int:
        return enviar_recalls_ausentes_job(dias=dias)

    @_celery_app_c11.task(name="app.worker.tasks.enviar_recalls_control")
    def _celery_c11_recall_control() -> int:
        return enviar_recalls_control_job()

except Exception:  # pragma: no cover
    pass
