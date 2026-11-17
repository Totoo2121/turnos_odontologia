# Design

## Context

Ver proposal.md. Stack FastAPI + SQLAlchemy + Alembic + Postgres 15+. Multi-tenant con RLS por tenant. Catálogo (profesionales/sillones/prestaciones/bloqueos) ya existe en C-05.

## Goals / Non-Goals

**Goals:** anti-solapamiento garantizado en DB; ciclo de vida de turnos; sobreturnos; reprogramación con traslado de seña; cancelación con antelación; agenda por día/semana.

**Non-Goals:** UI (C-07), turnero online (C-08), cobros MP (C-10).

## Decisions

- Usar `EXCLUDE USING gist` con `tstzrange(inicio, fin)` por (`profesional_id`) y (`sillon_id`), scoped por tenant vía RLS + condición `WHERE estado <> 'cancelado'` (turnos cancelados no ocupan hueco).
- `fin` calculado en dominio al crear (RN-AG-03), persistido.
- Bloqueo verificado en capa de aplicación consultando tabla `bloqueo` antes de insertar; el constraint de exclusión cubre turnos, no bloqueos.
- Sobreturno: flag `sobreturno=true`, sin validación de hueco de grilla, pero sigue validando exclusión de profesional/sillón.
- Reprogramación: transactional: validar destino, insertar nuevo, cancelar anterior, trasladar seña.
- Concurrencia: confiar en constraint de exclusión → 409 al IntegrityError.

## Risks / Trade-offs

- [Exclusión GIST requiere extensión btree_gist] → migración habilita `CREATE EXTENSION IF NOT EXISTS btree_gist`.
- [Turnos cancelados liberan hueco] → condición en constraint.
- [Carrera] → capturar IntegrityError y mapear a 409.

## Migration Plan

Migración 004: crear tabla `turno`, constraints de exclusión, índices. Rollback: drop table (los changes dependientes no existen aún).

## Open Questions

- Buffer por prestación vs global: se asume buffer en prestación (RN-AG-03). Confirmado.