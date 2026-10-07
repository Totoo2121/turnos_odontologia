# Design

## Context

C-01 dejó API + Alembic async + `shared.db.metadata` compartida; C-02 aportó `AuditMixin`, `BaseRepository[T]`, `UnitOfWork` y RLS + FORCE RLS por tabla de tenant; C-03 aportó `PermissionContext.require_role()` y tenant derivado del JWT. Ver `proposal.md` (Why) para la motivación. Este design cubre CÓMO añadir el catálogo sin romper esos contratos. Requisitos vinculantes en `specs/agenda-catalog/spec.md`.

Estado actual verificado en código: `backend/app/domain/models.py` (Tenant/Sucursal/Rol/Usuario/UserRol + tokens C-03), `backend/app/domain/mixins.py` (`AuditMixin`), migraciones `a1b2c3d4e5f6` (baseline) → `c02a1b2c3d4e5` → `c03a1b2c3d4e5`, routers en `backend/app/api/` (`auth.py`, `deps.py` con tenant-GUC + guards).

## Goals / Non-Goals

**Goals:**
- 5 tablas tenant-scopeadas con RLS/FORCE RLS, soft-delete y repositorios tipados reutilizando la base C-02.
- CRUD con validación Pydantic v2 estricta y matriz RBAC mínima (escritura propietario).
- Generador de huecos puro, determinista y testeable sin DB, reutilizable por C-06/C-08.
- Migración 003 + seed idempotente con datos ficticios.

**Non-Goals:**
- Tabla de horarios/jornada del profesional (no existe en KB 04; la ventana la pasa el llamador — ver D2).
- Endpoints de turnos, sobreturnos, turnero público, cobros, UI (C-06+).
- Backfill o triggers sobre turnos históricos (no existen aún; la inmutabilidad se garantiza por snapshot en C-06).

## Decisions

### D1 — Nuevo módulo `domain/agenda/` en vez de engordar `models.py`
Crear `backend/app/domain/agenda/{models.py,repositories.py,slots.py}` con `Profesional`, `Sillon`, `Prestacion`, `ProfesionalPrestacion`, `Bloqueo`; `models.py` raíz queda intacto (solo re-exporta si conviene). `Base` sigue atada a `shared.db.metadata` para que `alembic/env.py` no cambie.
- Alternativa: añadir todo a `models.py` — rechazada: el archivo ya supera 250 líneas y la arquitectura pide monolito modular por dominio (`agenda`, `clinica`, ...).

### D2 — Generador de huecos como función pura en capa application
`generate_slots(ventana_inicio, ventana_fin, duracion_min, buffer_min, turnos_ocupados[], bloqueos[]) -> list[Slot]` en `application/agenda_slots.py` (o `domain/agenda/slots.py` si el proyecto prefiere dominio puro): aritmética de intervalos en múltiplos de paso, `fin_slot = inicio + duracion + buffer`, solape con semántica `[inicio, fin)`. Sin I/O, sin reloj global (todo `timestamptz` explícito), sin tabla de horarios: el llamador (C-06 y el endpoint interno de consulta) pasa la ventana de jornada.
- Alternativa: procedimiento SQL o vista — rechazada: lógica de redondeo y motivos de bloqueo se testea mejor en Python y se reutiliza en turnero online sin round-trip.
- Alternativa: modelar `HorarioProfesional` ahora — rechazada: KB 04 no lo define; inventarlo rompería el contrato de capabilities. Se registra como pregunta abierta para C-06/C-07.

### D3 — RLS + FORCE RLS idéntico a 001/002 en las 5 tablas
Cada tabla con `tenant_id NOT NULL FK tenant`, policy `USING (tenant_id = current_setting('app.tenant_id')::uuid)`, `ENABLE ROW LEVEL SECURITY + FORCE`. `Rol` sigue siendo la única excepción global; `profesional_prestacion` hereda tenant del profesional (constraint + índice compuesto) para no crear huérfanos cross-tenant.
- Índices: `(tenant_id, nombre)` en prestacion/sillon único parcial donde `is_active`; `(tenant_id, profesional_id)`, `(tenant_id, sillon_id, inicio)` en bloqueo; FKs indexados.

### D4 — RBAC mínimo sobre `PermissionContext` existente
Escritura (POST/PATCH/DELETE) de los 4 recursos: `require_role("propietario")`. Lectura (GET/list): cualquier staff autenticado (`propietario|odontologo|recepcion|asistente`). Sin permisos nuevos ni cambios a la matriz C-03.
- Alternativa: permitir a recepción crear bloqueos — rechazada: CHANGES.md y matriz 03 reservan configuración de agenda al propietario; recepción opera turnos (C-06), no catálogo.

### D5 — Validación en borde con Pydantic v2, DB como última autoridad
Schemas estrictos: `duracion_min > 0`, `buffer_min >= 0`, `fin_bloqueo > inicio_bloqueo`, bloqueo con ≥1 objetivo, `seña_obligatoria → monto_seña > 0`, moneda fija ARS en seed. CHECKs espejo en migración (duración, rango, motivo enum) para que la DB rechace lo que el borde deje pasar.

### D6 — Migración 003 única, reversible, numerada
`c05a1b2c3d4e5_c05_agenda_catalog.py`: crea las 5 tablas + RLS + índices + CHECKs; `downgrade()` dropea en orden inverso. Sin ALTER a tablas existentes → rollback limpio, deploy sin downtime especial.

### D7 — Seed por claves naturales, idempotente, ficticio
`seed_catalogo(tenant_demo)`: upsert por `(tenant_id, nombre)` en prestaciones/sillón/profesional; bloqueos de feriados por `(tenant_id, inicio, profesional_id/sillon_id)`. Nombres de ejemplo marcados ficticios ("Dr. Demo Ficticio", "Box 1 (demo)"). Feriados AR del año como lista estática recargable, documentada como ejemplo no oficial.

### D8 — Inmutabilidad por snapshot (contrato para C-06, sin trabajo aquí)
Este change NO toca turnos (no existen). El contrato queda: C-06 copiará `duracion_min + buffer + precio + reglas` al crear cada turno; por tanto ningún trigger/backfill en C-05. La edición de prestación es un UPDATE normal versionado por `updated_at`.

## Risks / Trade-offs

- [Riesgo] Ventana de jornada sin modelo → el generador puede ofrecer huecos fuera de horario si el llamador pasa mal la ventana → Mitigación: firma exige ventana explícita + validación `ventana_fin > ventana_inicio`; documentar en docstring que la jornada la define el llamador hasta que exista modelo de horarios.
- [Riesgo] Feriados seed desactualizados → huecos ofrecidos en feriado real nuevo → Mitigación: seed documentado como ejemplo; dueños editan bloqueos por UI/API; C-11/C-06 nunca confían en el seed como fuente oficial.
- [Riesgo] `profesional_prestacion` huérfana cross-tenant → Mitigación: `tenant_id` redundante + UNIQUE `(profesional_id, prestacion_id)` + CHECK de mismo tenant vía trigger o validación en repositorio + test de aislamiento.
- [Trade-off] Sin endpoint público de huecos en C-05 (solo servicio interno + endpoint interno de consulta para validación) → C-08 deberá exponerlo; a cambio C-05 no abre superficie pública ni necesita rate-limit/captcha.

## Migration Plan

1. Aplicar `alembic upgrade head` (003) sobre DB vacía y sobre DB con C-01→C-03 (único path soportado).
2. Ejecutar seed de catálogo (idempotente, re-ejecutable en cada deploy).
3. Verificar: `pytest backend/tests -k catalogo` verde; smoke `GET /api/prestaciones` 200 como propietario, 403 como recepción en escritura.
- Rollback: `alembic downgrade -1` (dropea las 5 tablas); sin datos de turnos dependientes aún, no hay cascada.

## Open Questions

- Ninguna que cambie specs, enfoque o tasks. Queda como nota para C-06/C-07 (no bloquea): ¿de dónde viene la jornada laboral del profesional (tabla `horario` vs. configuración por tenant)? El generador ya acepta ventana explícita, así que la decisión puede esperar sin re-trabajo.
