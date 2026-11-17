# turnero-publico Specification

## Purpose

Permite a pacientes reservar turnos online sin cuenta a través de un enlace público y gestionarlos mediante un token de portal, reduciendo llamadas y habilitando el canal 24/7.

## Requirements

### Requirement: Reserva online sin cuenta
El sistema SHALL permitir reservar un turno desde `/reservar/{slug}` sin autenticación, exigiendo nombre y WhatsApp válido y validación anti-bots (rate-limit + captcha).

#### Scenario: Reserva exitosa
- **WHEN** el paciente completa datos válidos y elige un hueco disponible
- **THEN** el sistema crea el turno en estado `reservado` y devuelve confirmación inmediata en pantalla más enlace de portal.

#### Scenario: Hueco tomado en el ínterin
- **WHEN** el hueco elegido fue tomado concurrentemente
- **THEN** el sistema responde 409 con alternativas y ofrece alta en lista de espera.

### Requirement: Huecos válidos y sin sobreturnos
El sistema SHALL ofrecer solo huecos válidos (descontando turnos y bloqueos) y nunca ofrecer sobreturnos en el turnero online.

#### Scenario: Sin sobreturnos
- **WHEN** un paciente busca disponibilidad
- **THEN** el sistema no muestra ni permite reservar sobreturnos.

### Requirement: Portal del paciente
El sistema SHALL exponer `GET /p/{token}` y `POST /p/{token}/cancelar|reprogramar` para cancelar o reprogramar hasta `anticipacion_min_cancel_hs`.

#### Scenario: Cancelación dentro de plazo
- **WHEN** el paciente cancela dentro del plazo configurado
- **THEN** el turno se cancela y se libera el hueco.

#### Scenario: Cancelación fuera de plazo
- **WHEN** el paciente intenta cancelar fuera del plazo
- **THEN** el sistema rechaza la operación y muestra la política de cancelación.

### Requirement: Auto-liberación sin confirmación
El sistema SHALL liberar el hueco si el turno no se confirma antes del umbral configurable.

#### Scenario: Vencimiento sin confirmación
- **WHEN** un turno reservado no se confirma a tiempo
- **THEN** el turno se cancela y el hueco queda disponible.
