# Design — C-02 Core Models Multi-Tenant

## Context

C-01 entregó scaffolding ejecutable y verificado: `backend/app/shared/db.py` (engine asyncpg, `MetaData` con naming convention minúscula, `get_db` por request), `settings.py` fail-fast, `alembic/env.py` que lee `target_metadata` de `app.shared.db.metadata`, baseline `a1b2c3d4e5f6` vacía y CI verde. No existe ningún modelo: este change agrega el primer dominio real. Ver `proposal.md` (Why) y `specs/core-multitenant/spec.md` (contrato de comportamiento); este documento cubre el cómo. Restricciones duras aplicables: toda tabla de tenant lleva RLS + FORCE RLS; schema solo vía migración Alembic numerada; datos sintéticos ficticios; sin secretos en código; sin commit.

## Goals / Non-Goals

**Goals:**

- Cinco tablas con aislamiento demostrable en DB y en capa de acceso, encadenadas sobre la baseline sin reescribirla.
- Patrón de acceso reutilizable por todos los changes futuros (`BaseRepository[T]` + `UnitOfWork` tenant-scopeados).
- Seed demo que deja el sistema listo para C-03 (login/RBAC) en un comando.

**Non-Goals:**

- Sin endpoints HTTP (C-03 expone auth; C-05 en adelante el dominio). Sin hashing/JWT (C-03). Sin lógica multi-sucursal (E2/C-18). Sin auditoría append-only de eventos (C-17; el `AuditMixin` aquí es solo ciclo de vida de fila).

## Decisions

### D1. RLS + FORCE RLS en Migración 001, defensa en profundidad — [CONFIRM]

**Decisión:** la Migración 001 crea las políticas RLS junto con las tablas: `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` en `tenant`, `sucursal`, `usuario`, `user_rol`; políticas `USING (tenant_id = current_setting('app.tenant_id')::uuid)` para DML/SELECT; rol owner/superficie de migraciones y seed opera con `BYPASSRLS`/como owner (única excepción documentada). La capa app además filtra siempre por `tenant_id` (el repository lo exige como argumento, no opcional).
**Alternativas:** solo `WHERE` en app (descartada: un bug expone datos cruzados; viola regla dura AGENTS.md); RLS diferida a C-03/C-17 (descartada: C-01 la difirió explícitamente a este change como checklist CRÍTICO).
**Por qué:** el costo (un `SET LOCAL app.tenant_id` por transacción en `UnitOfWork`) es despreciable frente a aislar a nivel DB; convierte RN-SE-01 en garantía estructural, no en convención.

### D2. PostgreSQL 15 + asyncpg confirmado, SU-06 cerrada — [APPROVED-BY-DESIGN]

**Decisión:** tratar SU-06 como confirmada: C-01 ya implementa engine asyncpg, `docker-compose.yml` con `postgres:15+`, `test_db.py` verifica driver asyncpg y Alembic corre en modo async. Este change usa tipos Postgres nativos (`UUID gen_random_uuid()`, `timestamptz`, `CHECK`) sin capa de abstracción multi-motor.
**Alternativas:** mantener agnosticismo de motor (descartada: impediría exclusiones anti-solapamiento de C-06 y RLS, ambas Postgres-dependientes y ya decididas en KB/DD-03).

### D3. `Sucursal` mínima ahora, full en E2 — [CONFIRM]

**Decisión:** crear `sucursal(id UUID, tenant_id FK, nombre, direccion NULL, telefono NULL + AuditMixin)` con `UNIQUE(tenant_id, nombre)`; sin lógica multi-sucursal (sin resolución de sucursal por turno, sin permisos por sucursal). `sillon.sucursal_id NULLABLE` lo referencia en C-05; la gestión real multi-sucursal queda en E2/C-18 (pregunta media de `10_preguntas_abiertas.md` respondida así: tabla existe desde el día 1, comportamiento multi-sede no).
**Alternativas:** stub sin tabla (descartada: C-05 necesitaría crearla y rompería el orden de migraciones); full multi-sucursal ahora (descartada: fuera de scope C-02, sin requirements que lo pidan).

### D4. Soft-delete en entidades, hard-delete solo en el link `user_rol` — [CONFIRM]

**Decisión:** `Tenant`, `Sucursal`, `Usuario`, `Rol` llevan `AuditMixin` completo y jamás se borran físicamente desde repositorios (`delete()` = marca `deleted_at` + `is_active=false`; listados/`get` excluyen borrados por defecto con flag `include_deleted` explícito para admin). `user_rol` es fila de enlace sin ciclo de vida propio: alta/baja por `DELETE` físico (desasignar rol), con `created_at` para auditoría mínima; su `tenant_id` se deriva del usuario y se valida en escritura.
**Alternativas:** hard-delete general (descartada: pierde trazabilidad y rompe FKs futuras de turnos/HCE); soft-delete también en `user_rol` (descartada: acumula enlaces muertos y complica unicidad `(usuario_id, rol_id)` activa).
**Coherencia con spec:** el requirement de AuditMixin se verifica sobre usuario/sucursal (escenarios), no impone mixin al link; este diseño lo fija.

### D5. `password_hash` reservado NULLABLE, scheme en C-03 — [APPROVED-BY-DESIGN]

**Decisión:** `usuario.password_hash VARCHAR(255) NULL` existe desde 001 pero C-02 no implementa ni elige algoritmo: el seed deja marcador inválido que nunca autentica (`!UNSET-C03*`, documentado). C-03 elige (argon2id vs bcrypt), agrega `NOT NULL` + verificación/login y rota el seed a hash real; no hay duplicación de lógica de credenciales en este change.
**Alternativas:** elegir algoritmo ya (descartada: pertenece al threat model de C-03, que además define rate-limit, blacklist y claims JWT).

### D6. `Rol` como catálogo global sin `tenant_id`; `UserRol` porta el tenant — [CONFIRM]

**Decisión:** `rol(id UUID, nombre UNIQUE global, descripcion)` con exactamente 4 filas (`propietario|odontologo|recepcion|asistente`); sin `tenant_id`, sin RLS (catálogo inmutable, sin datos de tenant — excepción explícita y única a la regla RLS, solo lectura para app). `user_rol(usuario_id, rol_id, tenant_id FK, UNIQUE(usuario_id, rol_id))` con RLS por `tenant_id`; el repository valida que `user_rol.tenant_id == usuario.tenant_id`.
**Alternativas:** rol por tenant (descartada: cuadruplica catálogo, complica seed y matriz RBAC global de 03_actores_y_roles).
**Riesgo asumido:** rol global visible cross-tenant por diseño (solo nombres de rol, nunca datos); documentado en spec de aislamiento como no-dato-sensible.

### D7. Identificadores, naming y constraints físicos

UUID v4 (`gen_random_uuid()`) como PK en las 5 tablas; identificadores minúscula; reutilizar `NAMING_CONVENTION` de `db.py`; índice en cada FK; `UNIQUE(slug_reserva)` global con `CHECK (slug_reserva ~ '^[a-z0-9-]+$')`; `UNIQUE(tenant_id, email)` en usuario con normalización a minúsculas en app (sin CITEXT para no sumar extensión); `plan TEXT DEFAULT 'base'` sin CHECK (pricing propio aún abierto, IN-02); `moneda CHAR(3) DEFAULT 'ARS'`; `tenant.slug_reserva` indexado (turnero `GET /reservar/{slug}` en C-08 lo resuelve por slug). Modelos importados desde `app.shared.db.metadata` para que `env.py` los vea sin cambios.

### D8. Forma del `BaseRepository[T]` + `UnitOfWork`

`BaseRepository[T]` genérico async (`get`, `list`, `add`, `update`, `soft_delete`) que exige `tenant_id` en constructor y lo inyecta en cada query; `UnitOfWork` como async context manager que abre sesión corta (reúsa `get_session_factory`), ejecuta `SET LOCAL app.tenant_id`, expone repositorios y hace commit/rollback todo-o-nada; transacciones cortas y pool modesto heredado de C-01 (5+5). Sin queries crudas ad-hoc fuera de migraciones.

### D9. Seed idempotente por claves naturales, datos ficticios

Script `backend/app/infrastructure/seed_c02.py` (función `seed_c02(session)`, invocable por CLI/worker, no en import): upsert por `slug_reserva='demo-ficticia'`, por `rol.nombre` y por `admin` email `admin@demo-ficticia.invalid` (dominio `.invalid`, teléfono `+54 9 11 0000-0000`, todo marcado ficticio). Re-ejecutable sin duplicar; fuera del path de tests salvo test dedicado.

## Risks / Trade-offs

- [Risk] `SET LOCAL` olvidado en alguna sesión manual → política por defecto deniega todo (fail-closed: error visible, no fuga). Mitigación: solo `UnitOfWork`/seed fijan el GUC; test de aislamiento lo cubre.
- [Risk] RLS + FORCE RLS complica debugging en psql (tablas "vacías" sin GUC). Mitigación: documentar `SET app.tenant_id` en runbook del change; migraciones corren como owner.
- [Risk] `Rol` global sin RLS se lee como violación de la regla dura. Mitigación: excepción explícita aquí + test que afirma que `rol` no contiene `tenant_id` ni PII.
- [Risk] `password_hash` NULL temporalmente. Mitigación: marcador `!UNSET` imposible de verificar; C-03 lo endurece a NOT NULL (tracking en tasks como dependencia declarada).
- [Risk] Tests de aislamiento necesitan Postgres real (SQLite no soporta RLS). Mitigación: suite de este change corre contra servicio Postgres de compose/CI (patrón a heredar por C-05+); tests unitarios puros no tocan DB.

## Migration Plan

1. `alembic revision --autogenerate` NO a ciegas: escribir 001 a mano desde modelos, `down_revision = a1b2c3d4e5f6`, id estable nuevo.
2. `alembic upgrade head` en DB vacía + `alembic downgrade -1` + `upgrade` (reversibilidad probada en CI).
3. Seed: `python -m app.infrastructure.seed_c02` (idempotente, re-ejecutable).
4. Rollback: `downgrade -1` deja baseline intacta; seed no necesita rollback (demo data, re-ejecutable).
5. Validación: `pytest backend/tests/test_c02_*`, `mypy`, `ruff/black` (gates heredados de C-01).

## Open Questions

Ninguna que cambie specs, enfoque o tasks. Seguimiento declarado (no bloqueante): pricing/planes reales (IN-02) para endurecer `plan` con CHECK en change futuro; alcance regulatorio SU-04 antes del sprint clínico (C-12), no afecta a este change.
