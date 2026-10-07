# Tasks — C-02 Core Models Multi-Tenant

> Governance CRÍTICO: solo planning en este change; el apply posterior implementa sin commitear (regla dura). Datos 100% sintéticos ficticios. TDD (Red→Green→Triangulate→Refactor) en cada grupo con DB Postgres real para aislamiento/RLS.

## 1. Safety net + modelos base con AuditMixin

- [x] 1.1 Registrar baseline de tests C-01 en verde y verificar `pytest backend/tests/ -q` pasa antes de tocar código
- [x] 1.2 Implementar `AuditMixin` + modelos `Tenant/Sucursal/Rol/Usuario/UserRol` (UUID, minúsculas, `password_hash` NULL con marcador `!UNSET-C03*`, D3–D7 del design) y verificar `pytest backend/tests/test_c02_models.py -q` cubre slug único, default ARS y `updated_at` > `created_at`
- [x] 1.3 Implementar soft-delete del mixin (exclusión por defecto + `include_deleted`) y verificar `pytest backend/tests/test_c02_soft_delete.py -q` cubre borrado invisible + fila persistida con `deleted_at`

## 2. Repository genérico + UnitOfWork tenant-scopeados

- [x] 2.1 Implementar `BaseRepository[T]` (exige `tenant_id`, CRUD filtra por tenant) + `UnitOfWork` (sesión corta, `SET LOCAL app.tenant_id`, commit/rollback) y verificar `pytest backend/tests/test_c02_repository.py -q` cubre CRUD scopeado y rollback todo-o-nada ante fallo de unicidad
- [x] 2.2 Implementar tests de aislamiento RN-SE-01 (query cruzada vacía, get-by-id cruzado denegado/inexistente, `rol` global sin PII) y verificar `pytest backend/tests/test_c02_isolation.py -q` pasa contra Postgres real

## 3. Migración 001 + RLS/FORCE RLS

- [x] 3.1 Escribir Migración 001 a mano (`down_revision=a1b2c3d4e5f6`: 5 tablas, PKs/FKs indexadas, UNIQUE + CHECKs, RLS + FORCE RLS + políticas por `app.tenant_id`) y verificar `alembic upgrade head` crea las 5 tablas y `SELECT relrowsecurity, relforcerowsecurity FROM pg_class` las reporta activas
- [x] 3.2 Verificar reversibilidad con `alembic downgrade -1` (desaparecen tablas y políticas, baseline válida) seguido de `alembic upgrade head`, y verificar `alembic current` muestra 001
- [x] 3.3 Verificar enforcement DB con sesión sin GUC (lectura denegada/vacía fail-closed) y con GUC fijado (solo filas del tenant), y verificar el test dedicado pasa

## 4. Seed mínimo idempotente

- [x] 4.1 Implementar `seed_c02` (upsert por `slug_reserva='demo-ficticia'`, 4 roles, admin `admin@demo-ficticia.invalid` propietario con hash `!UNSET-C03*`, todo ficticio) y verificar doble ejecución deja 1 tenant + 4 roles + 1 admin sin duplicar ni error fatal
- [x] 4.2 Declarar dependencia C-03 en el seed (TODO trazable: hash real + `NOT NULL` de `password_hash`) y verificar el marcador está documentado en código y no autentica contra nada en este change

## 5. Integración y gates de calidad

- [x] 5.1 Ejecutar suite completa (`pytest backend/tests/ -q`), `mypy`, `ruff`/`black` y `openspec validate --change c-02-core-models-multitenant` (vía `cmd /c` si PowerShell bloquea) y verificar todo verde sin archivos fuera de `backend/` + este change y sin commit realizado
