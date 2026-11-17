# Design

## Context

Ver `proposal.md`. Reutiliza motor de agenda/huecos de C-06 y modelo `token_portal` de migración 004. No hay migración nueva.

## Goals / Non-Goals

**Goals:** endpoint público con rate-limit + captcha; carrera por hueco con 409 + alternativas; portal por token; auto-liberación por umbral.
**Non-Goals:** seña MP (C-10), lista de espera auto-relleno (C-09), notificaciones WA (C-11).

## Decisions

- Token portal firmado (JWT corto) en URL `/p/{token}`; validación server-side contra turno.
- Rate-limit por IP+slug (Redis) y captcha (reCAPTCHA v3 o hCaptcha) en POST.
- Hueco: optimistic locking / constraint de exclusión; carrera devuelve 409 con próximos 3 huecos.
- Auto-liberación: worker cron revisa `reservado` sin confirmación > umbral → cancela y libera; ofrece lista de espera (C-09 hook).
- Frontend: rutas públicas sin auth guard; componentes responsive.

## Risks / Trade-offs

- [Bot abuse] → captcha + rate-limit + validación WhatsApp.
- [Race conditions] → constraint DB + 409 con alternativas.
- [Token leak] → token de un solo uso / expiración.

## Migration Plan

Sin migración. Deploy frontend + backend. Rollback: revertir rutas.

## Open Questions

Ninguna bloqueante.