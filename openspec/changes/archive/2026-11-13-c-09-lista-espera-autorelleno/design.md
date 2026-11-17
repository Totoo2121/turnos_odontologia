# Design

## Context

Ver proposal.md. Reusa infraestructura de turnos (C-06) y cancelación (C-08). Worker asíncrono ya previsto en stack (Celery+Redis o APScheduler).

## Goals / Non-Goals

**Goals:** modelo + endpoints + worker de oferta/vencimiento + conversión a turno.
**Non-Goals:** notificaciones WA/email (C-11), UI de turnero (C-07).

## Decisions

- **Worker**: APScheduler in-process para MVP (simple, sin Redis extra); migrar a Celery si escala.
- **Vencimiento**: campo `ofrecida_hasta` timestamptz; job periódico cada minuto rota vencidas.
- **Matching**: por prestación + franja preferida (string enum mañana/tarde) + profesional opcional.
- **Conversión**: reutiliza servicio de creación de turno de C-06 (valida RN-AG-01/02/05).

## Risks / Trade-offs

- [Race] dos huecos liberados simultáneos → locking por tenant/prestación; mitigación: transacción + SELECT FOR UPDATE.
- [Vencimiento] job caído → ofertas vencidas quedan; mitigación: validación de vencimiento también en aceptación.

## Migration Plan

Migración Alembic 005 crea tabla `lista_espera` con RLS+FORCE RLS. Rollback: drop table.