# Proposal

## Why

La agenda del mostrador (US-002/US-003) no tiene frontend operativo: recepción no puede ver el día/semana, crear turnos en huecos válidos, ni ejecutar el ciclo de estados (confirmar, en sala, atender, cancelar, reprogramar, ausente) ni sobreturnos. Los endpoints de C-06 ya existen; falta la UI que los consume con guards por rol y validación en cliente de solape/bloqueo.

## What Changes

- Nueva capability `agenda-mostrador`: feature `frontend/src/features/agenda` con vistas día y semana por profesional y por sillón, estados y cobros visibles.
- Creación de turno solo en huecos válidos: solape/bloqueo rechazados con mensaje + motivo; sobreturno con confirmación de rol autorizado.
- Acciones de ciclo de vida contra endpoints de C-06: confirmar, en-sala, atender, cancelar, reprogramar, marcar ausente.
- Guards: recepcionista (y roles superiores) acceden; odontólogo ve su agenda; asistente según matriz.

## Capabilities

### New Capabilities
- `agenda-mostrador`: UI de agenda día/semana multi-profesional/multi-sillón con operatoria de recepción y ciclo de estados.

### Modified Capabilities
- (none) — no se alteran requirements de specs existentes; se consume `turnos-agenda` tal cual.

## Impact

- Frontend: `features/agenda`, `shared/ui` (calendario, modal, formulario), rutas en app shell.
- Consume API de C-06 (`GET /turnos/agenda`, `POST /turnos`, `PATCH /turnos/{id}/estado`, `POST /turnos/{id}/reprogramar`, `POST /turnos/{id}/cancelar`, `POST /turnos/sobreturno`) y C-05 (profesionales, sillones, prestaciones, huecos).
- Tests: render por rol recepción, creación en hueco válido/inválido, flujo de estados.
