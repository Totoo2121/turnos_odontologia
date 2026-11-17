# Design

## Context

Ver `proposal.md` - Why. El backend ya tiene el patrón de cambios recientes: modelos SQLAlchemy en `app/domain/agenda/models.py`, servicios de aplicación con un `Protocol` de store y una implementación in-memory para tests (`CobroService`), endpoints en `app/api/`, y jobs sync en `app/worker/tasks.py` registrados en `celery_app.beat_schedule` (C-10). La migración vigente es `c10...`; C-11 sigue con `c11...` (down_revision `c10a1b2c3d4e5`).

Restricciones relevantes:
- C-12 (pacientes) todavía no existe: no hay tabla `paciente` ni contacto del paciente persistido.
- `turno` ya guarda `token_portal`, estado, inicio/fin y referencias a prestación/profesional/sillón.
- Los endpoints públicos se declaran en `PUBLIC_PATHS` y exigen rate-limit + validación de firma.
- `settings.py` ya define `WA_BSP_TOKEN`, `WA_PHONE_ID`, `REMINDER_T48H_HS`, `REMINDER_T24H_HS`; no hay variables SMTP.

## Goals / Non-Goals

**Goals:**
- Aislar WhatsApp/email detrás de protocolos para poder testear sin red ni credenciales.
- Persistir recordatorios y plantillas con RLS multi-tenant y trazabilidad de envíos/confirmaciones.
- Jobs idempotentes y re-ejecutables sin duplicar mensajes.
- Funcionar aunque C-12 no exista, guardando snapshot de contacto en el turno.

**Non-Goals:**
- UI de bandeja de conversaciones o chat bidireccional completo.
- Edición de plantillas desde la UI (solo seed + lectura ).
- Facturación de mensajes / costos por BSP.
- Recordatorios push o SMS.

## Decisions

### Separación de puertos y adaptadores
- `NotificacionService` (aplicación) orquesta reglas: qué enviar, cuándo, reintentos y transiciones de estado.
- `RecordatorioStore` / `PlantillaStore` como `Protocol`, con `MemoryRecordatorioStore` para tests y un store SQLAlchemy para producción (mismo patrón que `CobroStore`).
- `WhatsAppClient` (`Protocol`) con `MetaCloudWhatsAppClient` por HTTP contra `graph.facebook.com` usando `WA_PHONE_ID`/`WA_BSP_TOKEN`; `FakeWhatsAppClient` en tests.
- `EmailClient` (`Protocol`) con `SmtpEmailClient` (smtplib en `run_in_executor` para no bloquear el event loop); `FakeEmailClient` en tests.
- Alternativa descartada: SDK propietario de un BSP específico → acopla el proyecto a un proveedor y complica tests.

### Snapshot de contacto en `turno`
Se agregan `contacto_whatsapp` y `contacto_email` (nullable) a `turno`. Motivo: C-11 no puede depender de C-12 y el job necesita un destinatario aunque el paciente aún no exista como entidad. Cuando C-12 cree `paciente`, el snapshot sigue siendo la fuente para el envío (inmutable para ese turno) y `paciente_id` queda como enlace. Alternativa descartada: tabla de contacto separada → duplica el ciclo de vida del turno.

### Migración 007
- `plantilla_mensaje`: `id`, `tenant_id`, `clave`, `canal (whatsapp|email)`, `idioma`, `version`, `cuerpo`, `meta_template_name?`, `activo`, `created_at`; `UNIQUE(tenant_id, clave, canal, idioma, version)`.
- `recordatorio`: `id`, `tenant_id`, `turno_id`, `paciente_id?`, `canal (whatsapp|email|interno)`, `tipo (t48h|t24h|confirmacion|recall_ausente|control|aviso_recepcion)`, `plantilla`, `destinatario?`, `enviar_at`, `estado (pendiente|enviado|fallido|confirmado|cancelado)`, `intentos`, `ultimo_error?`, `confirmado_at?`, `created_at`; `UNIQUE(turno_id, canal, tipo)` para idempotencia de outbound.
- `prestacion.intervalo_control_dias` (nullable): canaliza RN-NO-04 sin depender de una tabla de configuración nueva.
- RLS + FORCE RLS y policies por `tenant_id` en ambas tablas, replicando el patrón de C-10.
- No se agrega tabla de eventos del webhook: la idempotencia inbound se resuelve con transición first-write-wins (`confirmado_at` nulo → set) y un set de eventos procesados en proceso; los reintentos del proveedor no duplican efectos.

### Confirmación por webhook
- `POST /webhooks/whatsapp` valida `X-Hub-Signature-256` (HMAC-SHA256 de `WHATSAPP_WEBHOOK_SECRET`) y aplica rate-limit. Si el secreto no está configurado, en `dev` acepta y loguea warning; en `prod` rechaza (fail-closed).
- Extrae `turno_id` de `metadata`/payload y normaliza la respuesta: botón (`button.payload`), interactive reply o texto que matchee palabras clave de la plantilla (`CONFIRMAR`, `SI`, `SÍ`, `1`).
- Mapea por `turno.token_portal` o por metadata. Si el turno ya está `confirmado`, responde OK sin efectos (idempotente). Si está cancelado, responde OK sin cambiar estado.
- Persiste `confirmado_at` y canal; registra el evento en logs/auditoría de aplicación.

### Umbral sin confirmación y aviso a recepción
- Nuevo `CONFIRMATION_THRESHOLD_HS` (default 24) para el job. Alcanzado el umbral sin `confirmado_at`: crea `recordatorio` de `tipo=aviso_recepcion`, `canal=interno` (no envía externo) y dispara `ofertar_hueco_liberado` de C-09 si hay lista de espera compatible.
- Recepción consulta esas alertas con `GET /recordatorios?tipo=aviso_recepcion`.

### Recall y doble ausencia
- **Recall ausente**: job busca turnos `ausente` con `fin <= now - 7 días` sin `recordatorio` de `tipo=recall_ausente`; crea y envía plantilla de recall con oferta de reprogramación.
- **Doble ausencia**: se deriva de los últimos dos turnos del `paciente_id` en estado `ausente` (query ordenada por `fin`). No se agrega tabla de flags: el flag se expone como `requiere_sena` calculado. El turnero (C-08) lo consumirá en su integración posterior; C-11 deja el servicio `RequiereSenaService` y el job de recálculo.
- **Controles**: job busca turnos `atendido` cuya `prestacion.intervalo_control_dias` ya venció y no tengan `recordatorio` de `tipo=control`; crea y envía.

### Reintentos y fallback
- `NotificacionService.enviar` intenta WhatsApp; ante error transitorio reintenta con backoff exponencial (`NOTIF_MAX_INTENTOS`, default 3) usando `recordatorio.intentos`/`enviar_at`.
- Si se agota, envía email de respaldo; si también falla, marca `fallido` y crea `aviso_recepcion` interno + log de alerta.
- Los jobs son idempotentes por las constraints únicas y por el estado `enviado`.

### Worker
- `app/worker/tasks.py`: `enviar_recordatorios_programados`, `avisar_turnos_sin_confirmacion`, `enviar_recalls_ausentes`, `enviar_recalls_control`. Wrappers sync con `asyncio.run`, igual que C-10.
- `celery_app.py`: entradas de beat cada 15 min para recordatorios/avisos y cada 6 h para recalls.
- Ventanas y parámetros por env (`REMINDER_T48H_HS`, `REMINDER_T24H_HS`, `CONFIRMATION_THRESHOLD_HS`, `RECALL_AUSENTE_DIAS` default 7).

### Plantillas y seed
- Plantillas base: `recordatorio_t48h`, `recordatorio_t24h`, `confirmacion`, `recall_ausente`, `control`, `aviso_recepcion` en `whatsapp` y `email`, más `politica_cancelacion`.
- Seed idempotente por `(tenant_id, clave, canal, idioma, version)`; si ya existe no pisa la versión activa.

## Risks / Trade-offs

- [Proveedor BSP con API distinta a Meta Cloud] → el `Protocol` aísla el adaptador; cambiar de proveedor solo reemplaza `MetaCloudWhatsAppClient`.
- [Snapshot de contacto desactualizado] → el turno conserva el número con el que se reservó; cambios posteriores de teléfono aplican al siguiente turno. Es el comportamiento correcto para trazabilidad del recordatorio.
- [Webhook sin secreto en dev] → warning explícito y rechazo en `prod`; tests cubren ambos caminos.
- [Job duplicado en múltiples workers] → constraints únicas + estado first-write-wins; un segundo worker no reenvía.
- [Recall sin paciente formal (C-12)] → se usa `paciente_id` nullable y snapshot; cuando C-12 exista, se enlaza sin migración destructiva.
- [Timezone] → todas las fechas en UTC; la plantilla muestra hora local del tenant cuando esté disponible (v1: UTC-3 fijo para Argentina documentado en la plantilla).

## Migration Plan

1. `alembic upgrade head` con migración 007 (tablas + columnas + RLS).
2. Seed de plantillas (`python -m app.infrastructure.seed_c11` o seed existente invocado por el arranque de dev).
3. Configurar `WA_BSP_TOKEN`, `WA_PHONE_ID`, `WHATSAPP_WEBHOOK_SECRET` y SMTP en el entorno.
4. Desplegar API + worker con beat habilitado.
5. Rollback: deshabilitar beat entries, revertir migración 007 (drop de tablas/columnas). Los turnos no se pierden.

## Open Questions

- Proveedor BSP definitivo por tenant (Meta Cloud directo vs. BSP intermediario) se decide en onboarding comercial; el diseño no cambia porque el adaptador está detrás de un `Protocol`.
