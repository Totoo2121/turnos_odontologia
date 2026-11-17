# Tasks

## 1. Modelo, migración y seed

- [x] 1.1 Agregar `contacto_whatsapp` / `contacto_email` (nullable) a `Turno` y `intervalo_control_dias` (nullable) a `Prestacion` en `backend/app/domain/agenda/models.py`; verificar con `pytest backend/tests/test_agenda_models.py` y un test nuevo que las columnas existen.
- [x] 1.2 Crear modelos `PlantillaMensaje` y `Recordatorio` con RLS tenant en `backend/app/domain/notificaciones/models.py`; verificar tests de modelo y que `app.shared.db.metadata` las expone a Alembic.
- [x] 1.3 Crear migración `c11...` (down_revision `c10a1b2c3d4e5`) con tablas `plantilla_mensaje` y `recordatorio`, columnas nuevas, índices y políticas RLS/FORCE RLS; verificar `alembic upgrade head` y un test de migración que inspecciona tablas, columnas y policies.
- [x] 1.4 Crear seed idempotente de plantillas WA/email (`recordatorio_t48h`, `recordatorio_t24h`, `confirmacion`, `recall_ausente`, `control`, `aviso_recepcion`, `politica_cancelacion`); verificar que correrlo dos veces no duplica filas ni pisa versiones activas.

## 2. Configuración y adaptadores externos

- [x] 2.1 Extender `Settings` con `WHATSAPP_WEBHOOK_SECRET`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `CONFIRMATION_THRESHOLD_HS`, `RECALL_AUSENTE_DIAS` y `NOTIF_MAX_INTENTOS`; verificar test de settings y `.env.example` actualizado sin secretos reales.
- [x] 2.2 Implementar `WhatsAppClient` (`Protocol`) + `MetaCloudWhatsAppClient` en `backend/app/infrastructure/whatsapp_bsp.py` y un fake para tests; verificar que un error HTTP transitorio se propaga como error reintentable y un 4xx permanente como fallo definitivo.
- [x] 2.3 Implementar `EmailClient` (`Protocol`) + `SmtpEmailClient` en `backend/app/infrastructure/smtp.py` con envío en executor y fake de tests; verificar envío con SMTP fake y que un fallo de conexión se reporta sin romper el event loop.

## 3. Servicio de notificaciones y recordatorios

- [x] 3.1 Implementar `NotificacionService` con `RecordatorioStore` / `PlantillaStore` (`Protocol`) + stores in-memory y SQLAlchemy en `backend/app/application/notificaciones.py`; verificar unit tests de creación idempotente de recordatorios.
- [x] 3.2 Implementar el envío con plantilla aprobada por clave/canal/idioma y registro de estado (`pendiente`/`enviado`/`fallido`); verificar test de envío con plantilla activa y de fallo controlado con plantilla inexistente o inactiva.
- [x] 3.3 Implementar reintento con backoff, fallback a email y alerta `aviso_recepcion` al agotar intentos; verificar tests de falla transitoria (reintenta y luego email) y falla persistente (marca `fallido` + alerta).
- [x] 3.4 Implementar cálculo de ventanas T-48h/T-24h y selección de turnos activos sin recordatorio previo; verificar tests de ventana, turno ya recordado (no duplica) y turno cancelado/ausente (no recibe recordatorio).
- [x] 3.5 Implementar `RequiereSenaService` que deriva doble ausencia de los últimos dos turnos y expone `requiere_sena(paciente_id)`; verificar tests de dos ausencias consecutivas vs. ausencia intercalada con asistencia.

## 4. Webhook de confirmación

- [x] 4.1 Implementar `POST /webhooks/whatsapp` en `backend/app/api/whatsapp_webhook.py` con rate-limit y validación HMAC `X-Hub-Signature-256`; verificar 401 con firma inválida/ausente y 200 con firma válida, incluyendo el modo dev sin secreto y prod fail-closed.
- [x] 4.2 Parsear botón, interactive reply y palabras clave, resolver el turno y aplicar la transición a `confirmado` + `confirmado_at` + canal; verificar confirmación válida, turno ya confirmado (idempotente) y turno cancelado/inexistente (sin cambio).
- [x] 4.3 Registrar el router en `backend/app/main.py` y confirmar que `PUBLIC_PATHS` ya cubre `POST /webhooks/whatsapp`; verificar con test HTTP de que el endpoint no exige JWT.

## 5. Jobs del worker

- [x] 5.1 Implementar `enviar_recordatorios_programados` y `avisar_turnos_sin_confirmacion` en `backend/app/worker/tasks.py` con wrappers sync para Celery; verificar tests de envío en ventana, aviso al umbral sin confirmación y oferta a lista de espera.
- [x] 5.2 Implementar `enviar_recalls_ausentes` (7 días, sin duplicar) y `enviar_recalls_control` (intervalo de prestación); verificar tests de recall a los 7 días, no reenvío y control vencido.
- [x] 5.3 Registrar las entradas de beat en `backend/app/worker/celery_app.py` (recordatorios/avisos cada 15 min, recalls cada 6 h) y verificar con test de configuración del beat schedule.

## 6. API operativa e integración

- [x] 6.1 Exponer `GET /recordatorios?tipo=aviso_recepcion` (autenticado, scoped por tenant) para que recepción vea alertas y `GET /plantillas` (solo lectura, propietario/admin); verificar tests de rol, scoping y contenido.
- [x] 6.2 Escribir el test E2E del Flujo 2: turno activo → recordatorio T-48h/T-24h enviado → webhook de confirmación → turno `confirmado`; verificar que corre contra fakes y no requiere red ni credenciales reales.
- [x] 6.3 Documentar las variables de entorno nuevas y el flujo de plantillas en `README.md` / `.env.example`; verificar que la documentación coincide con los nombres reales de settings.

## Workflow follow-up

- Ejecutar `openspec validate c-11-notificaciones-whatsapp --strict` y corregir warnings antes de archivar.
- Archivar el change con `/opsx:archive c-11-notificaciones-whatsapp` y marcar `C-11` como `[x]` en `CHANGES.md`.
