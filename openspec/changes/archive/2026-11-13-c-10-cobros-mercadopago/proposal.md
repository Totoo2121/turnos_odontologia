# Proposal

## Why

Las reservas online que exigen seña quedan en estado `reservado-pendiente-pago` y no se acreditan automáticamente: hoy no existe integración con Mercado Pago ni manejo de webhook IPN. Sin esto, el hueco no se confirma ni se libera por vencimiento, violando RN-TU-04 y RN-AD-04, y bloqueando US-011 y el Flujo 1.

## What Changes

- Nueva capacidad `cobros-mercadopago`: creación de orden de pago (Checkout Pro) vinculada al turno al reservar con seña obligatoria.
- Endpoint público de retorno (success/failure/pending) con estado visible al paciente.
- Webhook IPN con validación de firma, idempotencia por `mp_payment_id` y acreditación que mueve el turno a `confirmado` (o anula + libera hueco si vence/rechaza).
- Job del worker que vence órdenes pendientes sin acreditación (RN-AD-04, RN-G-02).
- Exposición del estado de cobro en agenda (patrón FLAP) y en reportes de señas pendientes.
- Auditoría de eventos de cobro (RN-SE-05).

## Capabilities

### New Capabilities
- `cobros-mercadopago`: integración MP (orden, checkout, webhook IPN, idempotencia, vencimiento, estado de cobro en agenda).

### Modified Capabilities
- (ninguna a nivel de requisitos; turnos-agenda ya contempla estados, aquí se añade el flujo de pago)

## Impact

- Módulo `cobros` nuevo; endpoints en `/senias` y `/cobros`.
- Dependencias: SDK Mercado Pago, variables de entorno (MP_ACCESS_TOKEN, MP_WEBHOOK_SECRET).
- Requiere C-06 (turnos) archivado para vincular orden a turno.
- Afecta turnero público (checkout redirect) y agenda (estado de cobro).
