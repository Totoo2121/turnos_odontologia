# Design

## Context

Las tablas de dominio tienen `tenant_id` y el request lo fija con `SET LOCAL app.tenant_id`; la app usa Celery/Redis y storage privado. Las evoluciones y el ledger ya son append-only.

## Goals / Non-Goals

**Goals:** auditar eventos sensibles, filtrar por tenant en API y DB, exportar las filas del tenant y adjuntos/consentimientos, omitir credenciales y eliminar archivos temporales.

**Non-Goals:** definir respaldo de infraestructura, certificar cumplimiento legal, exportar credenciales/tokens de autenticación, retener paquetes a largo plazo.

## Decisions

- Migración 011 crea `audit_evento` y `exportacion`, ambas con FORCE RLS.
- Trigger impide UPDATE, DELETE y TRUNCATE de eventos; la auditoría registra recurso, evento, actor, método y ruta, sin IP, body ni texto clínico.
- El wiring normal de `create_app` registra eventos; apps de test/in-memory no realizan escrituras externas.
- Exportación se genera como ZIP con `datos.json`, manifiesto, adjuntos y consentimientos existentes; `password_hash`, tokens portal y denylist quedan excluidos.
- Owner solicita exportación. El worker guarda una clave privada con expiración de 30 minutos; descarga única o tarea de vencimiento la elimina.
- `GET /api/admin/auditoria` soporta filtros y paginación, solo propietario.

## Risks / Trade-offs

El tamaño del ZIP se materializa en memoria y requiere dimensionar el worker. Si un adjunto ya no existe en storage, queda indicado en el manifiesto. La política legal y los backups externos requieren validación separada.
