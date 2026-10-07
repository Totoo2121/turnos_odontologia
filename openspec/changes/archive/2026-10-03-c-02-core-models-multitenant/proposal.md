# Proposal — C-02 Core Models Multi-Tenant

## Why

C-01 dejó scaffolding ejecutable pero sin ningún modelo de dominio: no existe `tenant_id`, por lo que RN-SE-01 (aislamiento por tenant) es hoy inaplicable y C-03 (auth/RBAC) no tiene sobre qué apoyarse. Este change crea la base multi-tenant sobre la que se construye todo el dominio.

## What Changes

- Modelos SQLAlchemy 2.0 async: `Tenant` (`slug_reserva` único global, `plan`, `moneda` default ARS), `Sucursal` (columnas mínimas, full en E2), `Usuario`, `Rol`, `UserRol` (join explícito).
- `AuditMixin` (`is_active`, `created_at`, `updated_at`, `deleted_at`) + soft-delete como única vía de baja lógica; `BaseRepository[T]` genérico + `UnitOfWork` con scoping forzado por `tenant_id` (RN-SE-01).
- Migración Alembic 001 (`tenant`, `sucursal`, `usuario`, `rol`, `user_rol`) encadenada sobre baseline `a1b2c3d4e5f6`, incluyendo RLS + FORCE RLS (decisión (a) en design).
- Seed mínimo idempotente: 1 tenant demo ficticio + 4 roles (`propietario|odontologo|recepcion|asistente` según 03_actores_y_roles) + 1 usuario ADMIN propietario (password reservado, hash real en C-03).
- Tests: aislamiento multi-tenant (query cruzada denegada / invisible), CRUD repositorio genérico, soft-delete del mixin; datos 100% sintéticos ficticios.

## Capabilities

### New Capabilities

- `core-multitenant`: entidades base multi-tenant, patrones de acceso (repository + UoW con scoping forzado), RLS a nivel DB, seed mínimo y garantías de aislamiento RN-SE-01.

### Modified Capabilities

- Ninguna (no se cambian requirements de `platform-foundation`; la baseline Alembic se encadena, no se reescribe).

## Impact

- Afecta: `backend/app/domain/` (nuevos modelos), `backend/app/infrastructure/` (repository/UoW/seed), `backend/alembic/versions/` (Migración 001), `backend/tests/` (nuevos tests de aislamiento/CRUD/soft-delete).
- Dependencias: requiere C-01 archivado (scaffolding, settings, async session, baseline Alembic); desbloquea C-03 (JWT/RBAC necesita `Usuario`/`Rol`/`tenant_id`).
- Sin breaking changes (tablas nuevas, ninguna API pública todavía); sin secretos en código; sin commit (regla dura).
