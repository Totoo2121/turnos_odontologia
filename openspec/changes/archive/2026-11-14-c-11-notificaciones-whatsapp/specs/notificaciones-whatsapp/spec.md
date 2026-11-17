# Spec Delta

## Purpose

Automatiza el ciclo de comunicación con el paciente por WhatsApp Business API oficial y email de respaldo: recordatorios, confirmación de turnos, recall de ausentes y controles periódicos, con reintentos y alertas operativas.

## ADDED Requirements

### Requirement: Recordatorios automáticos T-48h y T-24h
El sistema MUST enviar recordatorios por WhatsApp y un email de respaldo para todo turno activo en las ventanas configurables `REMINDER_T48H_HS` y `REMINDER_T24H_HS`, registrando cada envío en `recordatorio` (RN-NO-01).

#### Scenario: Turno activo entra en ventana T-48h
- **WHEN** el worker detecta un turno activo a 48 horas o menos de su inicio sin recordatorio T-48h registrado
- **THEN** crea el registro de recordatorio, envía WhatsApp y email de respaldo, y deja el envío auditado

#### Scenario: Recordatorio duplicado evitado
- **WHEN** el worker vuelve a evaluar un turno que ya tiene el mismo recordatorio y ventana enviado
- **THEN** no lo reenvía y no crea un registro duplicado

### Requirement: Plantillas aprobadas y versionadas
El sistema MUST usar plantillas aprobadas y versionadas por tenant para cada mensaje saliente, identificadas por una clave estable; ningún mensaje se arma con texto libre (RN-NO-01, RN-NO-05).

#### Scenario: Envío con plantilla aprobada
- **WHEN** se programa un recordatorio de turno
- **THEN** el envío usa la plantilla aprobada vigente del tenant para esa clave y canal

#### Scenario: Plantilla inexistente o inactiva
- **WHEN** un job intenta enviar con una plantilla inexistente o inactiva
- **THEN** el envío falla de forma controlada, se registra el error y se alerta a operaciones sin usar texto improvisado

### Requirement: Confirmación por WhatsApp
El sistema MUST procesar la confirmación del paciente por botón o palabra clave, mover el turno a `confirmado` y registrar `confirmado_at` con el canal utilizado (RN-NO-02).

#### Scenario: Paciente confirma por botón
- **WHEN** llega una respuesta de WhatsApp asociada a un turno con confirmación válida
- **THEN** el turno pasa a `confirmado` y se audita la fecha/hora y el canal

#### Scenario: Confirmación de turno ya cancelado
- **WHEN** llega una confirmación para un turno cancelado o inexistente
- **THEN** el sistema no cambia el estado y responde sin error al proveedor

### Requirement: Webhook de WhatsApp autenticado
El endpoint público `POST /webhooks/whatsapp` MUST validar la firma del proveedor y aplicar rate-limit antes de procesar cualquier evento (regla dura de endpoints públicos).

#### Scenario: Firma inválida
- **WHEN** llega un webhook con firma inválida o ausente
- **THEN** el sistema responde 401 y no procesa el evento

#### Scenario: Evento duplicado
- **WHEN** el proveedor reintenta el mismo evento ya procesado
- **THEN** el sistema responde OK sin duplicar efectos sobre el turno

### Requirement: Aviso por falta de confirmación
El sistema MUST detectar los turnos que llegan al umbral configurable sin confirmación, avisar a recepción y ofrecer el hueco a la lista de espera (Flujo 2, RN-TU-02).

#### Scenario: Turno sin confirmar al umbral
- **WHEN** un turno alcanza el umbral de confirmación sin respuesta del paciente
- **THEN** se registra un aviso operativo para recepción y se dispara la oferta del hueco a lista de espera

### Requirement: Recall de ausentes
El sistema MUST enviar un mensaje de recall a los 7 días de un turno marcado `ausente`, ofreciendo reprogramación; dos ausencias consecutivas MUST marcar al paciente para exigir seña en su próxima reserva (RN-NO-03).

#### Scenario: Recall a los 7 días
- **WHEN** pasan 7 días desde un turno en estado `ausente` sin recall previo
- **THEN** se envía el mensaje de recall y se registra en `recordatorio`

#### Scenario: Doble ausencia exige seña
- **WHEN** un paciente acumula dos turnos consecutivos en estado `ausente`
- **THEN** su próxima reserva requiere seña aunque la prestación no la exija por defecto

### Requirement: Recall de controles periódicos
El sistema MUST generar recalls automáticos de controles según el intervalo configurado en la prestación (RN-NO-04).

#### Scenario: Control de ortodoncia vence
- **WHEN** transcurre el intervalo de control configurado para la prestación del último turno atendido
- **THEN** se encola y envía un recordatorio de control al paciente

### Requirement: Reintentos y fallback ante fallo del proveedor
El sistema MUST reintentar con backoff los envíos fallidos, usar email como fallback y generar una alerta operativa cuando el proveedor de WhatsApp falle de forma persistente (Flujo 2).

#### Scenario: Falla transitoria del BSP
- **WHEN** el proveedor de WhatsApp devuelve un error transitorio
- **THEN** el envío se reintenta con backoff y, si el reintento falla, se envía el email de respaldo

#### Scenario: Falla persistente
- **WHEN** un envío agota sus reintentos
- **THEN** se marca el recordatorio como fallido y se emite una alerta operativa para recepción

### Requirement: Canal oficial exclusivo
Todo mensaje MUST salir por la cuenta de WhatsApp Business API del tenant; el sistema MUST rechazar el uso de números personales o APIs no oficiales (RN-NO-05).

#### Scenario: Configuración sin cuenta Business
- **WHEN** un tenant no tiene configurada una cuenta Business API
- **THEN** el sistema no envía por WhatsApp, usa el fallback de email y reporta la configuración faltante
