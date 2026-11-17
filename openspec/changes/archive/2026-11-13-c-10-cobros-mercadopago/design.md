# Design

## Context

Ver proposal.md - Why. Módulo `cobros` nuevo en monolito modular; depende de turnos (C-06). SDK Mercado Pago. Webhook IPN público requiere validación de firma y rate-limit (regla dura).

## Goals / Non-Goals

**Goals:** Orden MP vinculada al turno; checkout redirect; webhook IPN idempotente; vencimiento por worker; estado de cobro en agenda/reportes.

**Non-Goals:** Facturación ARCA (etapa 2); cobro de saldos en mostrador (C-16); reembolsos automáticos (política manual v1).

## Decisions

- **SDK oficial MP** (mercadopago) en backend; no frontend SDK. Alternativa: API REST directa — descartada por mantenimiento de firma/webhook.
- **Webhook IPN** con verificación de firma HMAC; idempotencia por `mp_payment_id` (unique en tabla `pago`).
- **Estados de turno**: `reservado-pendiente-pago` → `confirmado` (acreditado) o `cancelado` (vencido/rechazado). RN-G-02: vencimiento prevalece.
- **Worker**: job periódico que vence órdenes sin acreditación tras plazo configurable (default 24h) y libera hueco + ofrece a lista de espera.
- **Tabla `pago`**: tenant_id, turno_id, mp_payment_id (unique), mp_order_id, monto, moneda, estado, created_at, acreditado_at.

## Risks / Trade-offs

- [IPN duplicado/reordenado] → idempotencia + transacción DB.
- [Webhook no llega] → worker de vencimiento + reconciliación manual.
- [Firma inválida] → rechazo 401 + log auditoría.

## Migration Plan

Migración Alembic nueva para tabla `pago` + columna en turno. Deploy con env vars MP. Rollback: revertir migración y deshabilitar checkout.

## Open Questions

Ninguno bloqueante.
