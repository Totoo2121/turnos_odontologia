# Proposal

## Why

El MVP contiene HCE, adjuntos, turnos y cobros, pero aún no registra una línea de auditoría uniforme ni permite recuperar todos los datos del tenant. C-17 implementa RN-SE-04/05 con exportación verificable y temporal.

## What Changes

- Agregar `audit_evento` con RLS + FORCE RLS y bloqueo de UPDATE/DELETE/TRUNCATE.
- Registrar lecturas clínicas, cambios de agenda/cobros, reportes y exportaciones sin guardar cuerpos, IP ni datos clínicos en los eventos.
- Exponer auditoría solo a propietario.
- Solicitar exportación por worker, generar ZIP con JSON y archivos clínicos, limitarla al tenant y permitir una descarga dentro de 30 minutos.
- Borrar el paquete al descargarlo o al vencer.
- Migración 011 añade `audit_evento` y metadatos temporales `exportacion`.

## Capabilities

### New Capabilities

- `auditoria-exportacion`: trazabilidad append-only y exportación completa del tenant.

### Modified Capabilities

- `identity-auth`: se auditan las superficies autenticadas que leen HCE o cambian agenda/cobros; la autorización existente no cambia.

## Impact

- Backend: modelos admin, dependencia de auditoría, endpoints `/api/admin`, tareas Celery y almacenamiento privado.
- Base: Alembic 011 con RLS y trigger inmutable.
- Operación: worker Celery y Redis ya usados por el proyecto; exportación depende del backend de almacenamiento configurado.
- Antes del lanzamiento debe validarse con asesor legal la política de protección de HCE y exportaciones.
