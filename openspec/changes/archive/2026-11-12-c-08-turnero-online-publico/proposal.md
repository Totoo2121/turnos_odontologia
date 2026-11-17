# Proposal

## Why

El consultorio no ofrece reservas online: los pacientes deben llamar. C-06 dejó el motor de agenda/huecos y C-07 la UI de mostrador; falta el canal público 24/7 para captar reservas sin cuenta, con portal para cancelar/reprogramar, según US-010 y RN-TU-01..03.

## What Changes

- Endpoints públicos `GET /reservar/{slug}` (prestaciones → profesionales → huecos) y `POST /reservar/{slug}/turnos` (crea `reservado`, carrera por hueco → 409 + alternativas + lista de espera).
- `GET /p/{token}` y `POST /p/{token}/cancelar|reprogramar` hasta `anticipacion_min_cancel_hs` (RN-TU-03), política visible al reservar.
- Rate-limit + captcha en rutas públicas; sin cuenta; validación nombre + WhatsApp (RN-TU-01).
- Auto-liberación de hueco si no hay confirmación antes del umbral (RN-TU-02).
- Turnero online nunca ofrece sobreturnos (RN-G-03).
- Frontend público responsive del turnero + portal.
- Sin migración nueva (usa `token_portal` de 004).

## Capabilities

### New Capabilities
- `turnero-publico`: reserva online 24/7 por enlace + portal del paciente.

### Modified Capabilities
- (ninguna)

## Impact

Backend: routers públicos, servicios de huecos/turnos, token portal. Frontend: páginas públicas `/reservar/:slug`, `/p/:token`. Dependencias: C-06. Tests: reserva sin cuenta, 409 carrera concurrente, cancelación dentro/fuera de plazo, rate-limit + captcha.