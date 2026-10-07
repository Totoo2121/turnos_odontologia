# Proposal

## Why

Sin catálogo de agenda (profesionales, sillones, prestaciones, bloqueos) no existe base para crear turnos ni generar huecos. C-05 es el primer change de dominio tras Auth/RBAC y desbloquea todo el núcleo de turnos (C-06 y siguientes en el camino crítico).

## What Changes

- Modelos de dominio `Profesional`, `Sillon`, `Prestacion`, `Bloqueo` + tabla de unión `profesional_prestacion`, todos multi-tenant con `AuditMixin`, RLS + FORCE RLS y soft-delete.
- CRUD protegidos por RBAC: `/api/profesionales`, `/api/sillones`, `/api/prestaciones`, `/api/bloqueos` (lectura: recepcion+; escritura: propietario; odontólogo ve sus habilitaciones).
- Regla de inmutabilidad de duración: cambiar `duracion_min`/`buffer` de una prestación NO altera turnos ya creados (cada turno congela su duración al crearse en C-06).
- Generador de huecos (slot generator) puro y testeable: múltiplos de duración sobre grilla del profesional descontando turnos existentes + bloqueos (RN-AG-04), expuesto como servicio de dominio reutilizable por C-06/C-08 (sin endpoint público propio en este change, solo uso interno + endpoint interno de consulta para validación).
- Migración Alembic 003 versionada y reversible (`profesional`, `sillon`, `prestacion`, `profesional_prestacion`, `bloqueo`) con índices por `(tenant_id, ...)` y constraints (`duracion_min > 0`, bloqueo con al menos un objetivo).
- Seed idempotente con datos ficticios: 5 prestaciones ejemplo (consulta 30', limpieza 45', conducto 90', corona 60', ortodoncia control 30'), 1 sillón "Box 1", 1 profesional demo con prestaciones habilitadas, feriados nacionales AR del año como bloqueos.

## Capabilities

### New Capabilities

- `agenda-catalog`: catálogo configurable de agenda — profesionales, sillones, prestaciones y bloqueos más generación de huecos. Es el vocabulario de oferta de la agenda sobre el que turnos, turnero online y reportes construyen.

### Modified Capabilities

<!-- Ninguna: no se cambian requisitos de capabilities existentes (core-multitenant e identity-auth se reutilizan sin modificar). -->

## Impact

- **Backend**: nuevo módulo `backend/app/domain/agenda/` (modelos, repositorios, servicio de huecos), routers en `backend/app/api/`, migración 003, seed ampliado. Reutiliza `BaseRepository`, `UnitOfWork`, `AuditMixin` y `PermissionContext` de C-02/C-03.
- **DB**: 5 tablas nuevas + RLS; sin cambios a tablas existentes.
- **APIs**: 4 recursos CRUD nuevos (versionados bajo `/api/`); ningún endpoint existente cambia → no breaking.
- **Dependencias**: requiere C-03 archivado (RBAC + tenant scoping). Desbloquea C-06 (`turnos-antissolapamiento`).
- **Fuera de alcance**: turnos, sobreturnos, turnero público, cobros, notificaciones, UI de agenda (C-06/C-07 en adelante). Sin frontend en este change salvo validación vía API.
- **Riesgos**: feriados AR como seed pueden quedar desactualizados → se documentan como datos ejemplo recargables, no como fuente oficial.
