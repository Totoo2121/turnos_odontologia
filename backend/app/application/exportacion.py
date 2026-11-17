"""C-17: complete tenant data export with a short, enforced download window."""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import uuid
import zipfile
from typing import Any

from sqlalchemy import select, text

import app.domain  # noqa: F401 - register all tenant domain tables in metadata
from app.domain.admin.models import AuditEvento, Exportacion
from app.infrastructure.storage import build_storage
from app.shared.db import get_session_factory, metadata

EXCLUDED_COLUMNS = {"usuario": {"password_hash"}, "turno": {"token_portal"}}
EXCLUDED_TABLES = {"exportacion", "revoked_token", "portal_token", "rol"}


def _json_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


async def _tenant_payload(
    session: Any, tenant_id: uuid.UUID
) -> tuple[dict[str, list[dict[str, Any]]], list[tuple[str, str]]]:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    payload: dict[str, list[dict[str, Any]]] = {}
    files: list[tuple[str, str]] = []
    for table in metadata.sorted_tables:
        if table.name in EXCLUDED_TABLES or "tenant_id" not in table.c:
            continue
        result = await session.execute(
            select(table)
            .where(table.c.tenant_id == tenant_id)
            .order_by(next(iter(table.primary_key.columns)))
        )
        excluded = EXCLUDED_COLUMNS.get(table.name, set())
        records: list[dict[str, Any]] = []
        for row in result.mappings():
            record = {
                key: _json_value(value)
                for key, value in row.items()
                if key not in excluded
            }
            records.append(record)
            if table.name == "adjunto" and record.get("storage_key"):
                files.append((
                    str(record["storage_key"]),
                    f"adjuntos/{record['id']}/{record.get('nombre_original') or 'archivo'}",
                ))
            if table.name == "consentimiento" and record.get("pdf_storage_key"):
                files.append((str(record["pdf_storage_key"]), f"consentimientos/{record['id']}.pdf"))
        if records:
            payload[table.name] = records

    tenant_table = metadata.tables.get("tenant")
    if tenant_table is not None:
        rows = await session.execute(select(tenant_table).where(tenant_table.c.id == tenant_id))
        payload["tenant"] = [
            {key: _json_value(value) for key, value in row.items()}
            for row in rows.mappings()
        ]
    role_table = metadata.tables.get("rol")
    if role_table is not None:
        role_rows = await session.execute(select(role_table.c.id, role_table.c.nombre, role_table.c.descripcion))
        payload["catalogo_roles"] = [
            {key: _json_value(value) for key, value in row.items()}
            for row in role_rows.mappings()
        ]
    return payload, files


async def generar_exportacion(exportacion_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            job = await session.scalar(select(Exportacion).where(
                Exportacion.id == exportacion_id,
                Exportacion.tenant_id == tenant_id,
            ))
            if job is None:
                return
            job.estado = "procesando"

    try:
        async with factory() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                payload, files = await _tenant_payload(session, tenant_id)

        output = io.BytesIO()
        missing_files: list[str] = []
        storage = build_storage()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "datos.json",
                json.dumps(payload, ensure_ascii=False, indent=2, default=_json_value),
            )
            for key, archive_name in files:
                try:
                    data = await storage.get(key)
                except Exception:
                    missing_files.append(archive_name)
                    continue
                safe_parts = archive_name.replace("\\", "/").split("/")
                safe_name = "/".join(
                    re.sub(r"[^a-zA-Z0-9._ -]", "_", part).replace("..", "_")
                    for part in safe_parts
                )
                archive.writestr(f"archivos/{safe_name}", data)
            archive.writestr("manifest.json", json.dumps({
                "tenant_id": str(tenant_id),
                "generado_at": dt.datetime.now(dt.UTC).isoformat(),
                "formato": "JSON UTF-8 + archivos originales",
                "archivos_no_disponibles": missing_files,
            }, ensure_ascii=False, indent=2))

        key = f"exportaciones/{tenant_id}/{exportacion_id}.zip"
        await storage.put(key, output.getvalue(), "application/zip")
        now = dt.datetime.now(dt.UTC)
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                    {"tenant_id": str(tenant_id)},
                )
                job = await session.scalar(select(Exportacion).where(
                    Exportacion.id == exportacion_id,
                    Exportacion.tenant_id == tenant_id,
                ))
                if job is None:
                    await storage.delete(key)
                    return
                job.estado, job.storage_key = "lista", key
                job.generada_at = now
                job.vence_at = now + dt.timedelta(minutes=30)
                session.add(AuditEvento(
                    tenant_id=tenant_id,
                    actor_usuario_id=job.solicitada_por_usuario_id,
                    evento="exportacion_generada",
                    recurso="exportacion",
                    recurso_id=str(exportacion_id),
                    metodo="WORKER",
                    ruta="/api/admin/exportacion",
                ))
        try:
            from app.worker.tasks import limpiar_exportacion_job

            limpiar_exportacion_job.apply_async(
                args=(str(tenant_id), str(exportacion_id)), countdown=30 * 60
            )
        except Exception:
            # The download endpoint enforces expiry; this only expedites cleanup.
            pass
    except Exception:
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                    {"tenant_id": str(tenant_id)},
                )
                job = await session.scalar(select(Exportacion).where(
                    Exportacion.id == exportacion_id,
                    Exportacion.tenant_id == tenant_id,
                ))
                if job is not None:
                    job.estado, job.error_code = "fallida", "exportacion_no_disponible"


async def limpiar_exportacion(tenant_id: uuid.UUID, exportacion_id: uuid.UUID) -> bool:
    factory = get_session_factory()
    now = dt.datetime.now(dt.UTC)
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            job = await session.scalar(select(Exportacion).where(
                Exportacion.id == exportacion_id,
                Exportacion.tenant_id == tenant_id,
            ))
            if job is None or job.estado != "lista" or job.vence_at is None or job.vence_at > now:
                return False
            key = job.storage_key
    if key:
        await build_storage().delete(key)
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            job = await session.scalar(select(Exportacion).where(
                Exportacion.id == exportacion_id,
                Exportacion.tenant_id == tenant_id,
            ))
            if job is not None:
                job.estado, job.storage_key = "vencida", None
    return True
