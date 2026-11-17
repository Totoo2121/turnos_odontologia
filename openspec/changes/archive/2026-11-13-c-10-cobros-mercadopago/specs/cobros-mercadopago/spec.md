# Spec Delta

## Purpose

Integra Mercado Pago para el cobro de señas vinculadas a turnos reservados online, incluyendo creación de orden, checkout, webhook IPN con idempotencia, acreditación o vencimiento, y exposición del estado de cobro en la agenda.

## ADDED Requirements

### Requirement: Creación de orden de pago al reservar con seña
El sistema SHALL crear una orden de Mercado Pago cuando una reserva online corresponda a una prestación con seña obligatoria, vinculándola al turno en estado `reservado-pendiente-pago`.

#### Scenario: Reserva con seña genera orden
- **WHEN** un paciente reserva un turno cuya prestación exige seña
- **THEN** el sistema crea la orden MP, retorna la URL de checkout y deja el turno en `reservado-pendiente-pago`

### Requirement: Webhook IPN acredita o vence
El sistema SHALL procesar el webhook IPN de Mercado Pago validando firma y aplicando idempotencia por `mp_payment_id`; al acreditarse, el turno pasa a `confirmado`; al rechazarse o vencer, se anula la reserva y se libera el hueco.

#### Scenario: Pago acreditado
- **WHEN** llega IPN con pago aprobado para una orden existente
- **THEN** el turno pasa a `confirmado` y se envía confirmación por WhatsApp + email

#### Scenario: Pago vencido o rechazado
- **WHEN** la orden vence sin acreditación o el pago es rechazado
- **THEN** la reserva se anula (`cancelado`), el hueco se libera y se ofrece a lista de espera

#### Scenario: IPN duplicado
- **WHEN** llega un IPN con un `mp_payment_id` ya procesado
- **THEN** el sistema responde OK sin efectos secundarios (idempotencia)

### Requirement: Vencimiento automático por worker
El sistema SHALL, mediante el worker, vencer órdenes pendientes sin acreditación dentro del plazo configurado, liberando el hueco (RN-AD-04 por encima de RN-TU-04).

#### Scenario: Orden vencida por worker
- **WHEN** una orden lleva más del plazo sin acreditación
- **THEN** el worker anula la reserva y libera el hueco

### Requirement: Estado de cobro visible en agenda
El sistema SHALL exponer el estado de cobro MP del turno en la agenda y reportes (señas pendientes).

#### Scenario: Recepción ve estado de cobro
- **WHEN** la recepción consulta la agenda
- **THEN** cada turno con seña muestra estado de cobro (pendiente/acreditado/vencido)
