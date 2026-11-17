# Proposal

## Why

Cuando un turno se cancela o libera un hueco, hoy no hay mecanismo para reasignarlo automáticamente a pacientes en espera. Lista de espera con auto-relleno (US-012) reduce huecos vacíos y mejora tiempos de atención, ofreciendo el hueco compatible por orden de antigüedad con vencimiento y rotando al siguiente si vence.

## What Changes

- Nuevo modelo `ListaEspera` (`paciente_id`, `prestacion_id`, `profesional_id?`, `franja_preferida`, `estado`, `created_at`) + migración 005.
- Endpoints `POST /lista-espera`, `GET /lista-espera` (alta/consulta por tenant).
- Worker que ante hueco liberado ofrece al compatible más antiguo (RN-TU-05) con vencimiento; si vence, pasa al siguiente.
- Aceptación convierte la oferta en turno normal (respecta RN-AG-01/02/05 y anti-solapamiento).
- Estados: `activa | ofrecida | convertida | vencida`.

## Capabilities

### New Capabilities
- `lista-espera`: alta/consulta en lista de espera y auto-relleno de huecos liberados por orden de antigüedad/preferencia con oferta con vencimiento (RN-TU-05).

### Modified Capabilities
- (ninguna) — la conversión reutiliza las reglas existentes de `turnos-agenda`.

## Impact

- Backend: nuevo router `lista_espera`, modelo, migración Alembic 005, worker/scheduler.
- DB: tabla `lista_espera` con RLS + FORCE RLS (multi-tenant).
- Integración con cancelación de turnos (C-06) para disparar oferta.
- Tests de orden por antigüedad/preferencia, vencimiento rota al siguiente, conversión respeta RN-AG-01/02/05.