# Proposal

## Why

Hoy los turnos se crean y se cobran, pero el sistema no avisa nada: no hay recordatorios T-48h/T-24h, no se procesa la confirmación del paciente por WhatsApp y no existe recall de ausentes ni de controles periódicos. Sin esto se incumplen RN-NO-01..05, quedan sin cubrir US-020/US-021 y el Flujo 2, y el ausentismo sigue siendo el principal agujero operativo del consultorio.

## What Changes

- Nueva capacidad `notificaciones-whatsapp`: envío full-cycle por WhatsApp Business API oficial del tenant (nunca números personales ni API no oficial, RN-NO-05) con email SMTP como respaldo.
- Plantillas aprobadas y versionadas por tenant (`plantilla_mensaje`), con claves estables para recordatorio, confirmación, recall y aviso a recepción.
- Worker periódico que detecta turnos activos en ventana T-48h/T-24h (`REMINDER_T48H_HS`, `REMINDER_T24H_HS`), registra `recordatorio` y envía por WA + email de respaldo (RN-NO-01).
- Webhook público `POST /webhooks/whatsapp` con validación de firma BSP: botón/palabra clave de confirmación mueve el turno a `confirmado` y audita `confirmado_at` + canal (RN-NO-02).
- Sin confirmación al umbral: aviso operativo a recepción y oferta del hueco a lista de espera (Flujo 2).
- Recall automático: ausente → mensaje a los 7 días con oferta de reprogramación; dos ausencias consecutivas marcan al paciente como `requiere_sena` (RN-NO-03). Controles periódicos por intervalo de prestación (RN-NO-04).
- Reintento con backoff, fallback a email y alerta operativa ante fallo del BSP (Flujo 2).
- Migración 007: `recordatorio`, `plantilla_mensaje` y snapshot de contacto (`contacto_whatsapp`, `contacto_email`) en `turno`, para que el envío no dependa de que C-12 (pacientes) ya exista.
- Seed de plantillas WA/email y política de cancelación por defecto.

## Capabilities

### New Capabilities
- `notificaciones-whatsapp`: automatización de recordatorios, confirmación por WhatsApp, fallback email, recall de ausentes/controles, reintentos y alertas operativas.

### Modified Capabilities

(ninguna: el cambio de columnas de contacto en `turno` es soporte de implementación y no altera requisitos existentes de `turnos-agenda`)

## Impact

- Backend: módulo `notificaciones` (servicio de aplicación), `infrastructure/whatsapp_bsp.py`, `infrastructure/smtp.py`, worker Celery/beat, endpoint público de webhook, router en `app/main.py`.
- DB: migración 007 con `recordatorio`, `plantilla_mensaje` y columnas de contacto en `turno`; RLS + FORCE RLS en tablas nuevas.
- Config: nuevos env vars SMTP (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`) y `WHATSAPP_WEBHOOK_SECRET`; se reutilizan `WA_BSP_TOKEN`, `WA_PHONE_ID`, `REMINDER_T48H_HS`, `REMINDER_T24H_HS`.
- Integraciones externas: WhatsApp Business API (BSP oficial) + SMTP; sin SDK propietario obligatorio (adaptador HTTP detrás de un protocolo).
- Depende de C-06 (turnos) archivado; no depende de C-12.
