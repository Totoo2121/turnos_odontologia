# Proposal

## Why

C-06 implementa el núcleo de la agenda: la entidad `Turno` con anti-solapamiento garantizado a nivel base de datos, su ciclo de vida y los sobreturnos. Sin él no hay agenda operativa ni turnero online (C-08) ni cobros (C-10). Las reglas RN-AG-01/02 exigen que el anti-solapamiento sea un constraint de exclusión Postgres, verificable con PostgreSQL MCP, no solo validación en código.

## What Changes

- Nueva entidad `Turno` con estados y origen, `fin = inicio + duración + buffer` (RN-AG-03).
- Constraints de exclusión Postgres por (`profesional_id`, rango) y (`sillon_id`, rango) (RN-AG-01/02).
- Endpoints: `POST /turnos`, `PATCH /turnos/{id}/estado`, `POST /turnos/{id}/reprogramar`, `POST /turnos/{id}/cancelar`, `POST /turnos/sobreturno`, `GET /turnos/agenda`.
- Migración 004: tabla `turno` + constraints + índices.
- Tests de solape DB, bloqueo, sobreturno, reprogramación con seña, 409 concurrente.

## Capabilities

### New Capabilities

- `turnos-agenda`: ciclo de vida de turnos, anti-solapamiento DB, sobreturnos, reprogramación y cancelación.

### Modified Capabilities

- (ninguna)

## Impact

Afecta backend (modelos, repositorios, endpoints, migración Alembic 004), tests, y depende de C-05 (catálogo). Consume skill `odontologia-reglas-negocio` para RN-AG-01..08 y RN-G-03. Verificación de constraints/solapes vía PostgreSQL MCP server.