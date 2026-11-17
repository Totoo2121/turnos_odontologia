# Tasks

## 1. Backend endpoints públicos

- [x] 1.1 Router `GET /reservar/{slug}` (prestaciones→profesionales→huecos) y verificar respuesta JSON
- [x] 1.2 `POST /reservar/{slug}/turnos` crea `reservado`, carrera → 409 + alternativas; verificar test de concurrencia
- [x] 1.3 Portal `GET /p/{token}` y cancelar/reprogramar; verificar plazos
- [x] 1.4 Rate-limit + captcha middleware; verificar bloqueo tras N requests

## 2. Auto-liberación

- [x] 2.1 Worker cron libera huecos sin confirmación; verificar test de vencimiento

## 3. Frontend público

- [x] 3.1 Páginas `/reservar/:slug` y `/p/:token` responsive; verificar build
- [x] 3.2 Tests E2E reserva sin cuenta

## 4. Integración

- [x] 4.1 Verificar flujo completo reserva→portal→cancelación