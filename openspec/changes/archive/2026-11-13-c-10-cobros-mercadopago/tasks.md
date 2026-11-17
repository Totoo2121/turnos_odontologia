# Tasks

## 1. Modelo y migración

- [x] 1.1 Crear migración Alembic para tabla `pago` y campo `mp_order_id` en turno; verificar que `alembic upgrade head` aplica sin errores.
- [x] 1.2 Definir modelo SQLAlchemy `Pago` con RLS tenant; verificar tests de modelo.

## 2. Integración Mercado Pago

- [x] 2.1 Implementar servicio `cobros` que crea orden MP y vincula al turno; verificar unit test de creación.
- [x] 2.2 Implementar endpoint público de checkout redirect y retorno; verificar respuesta 200 con URL.

## 3. Webhook IPN

- [x] 3.1 Implementar endpoint IPN con validación de firma HMAC y idempotencia por `mp_payment_id`; verificar tests de firma e idempotencia.
- [x] 3.2 Implementar acreditación (turno → confirmado) y anulación+vencimiento (turno → cancelado + liberar hueco); verificar tests de transición de estado.

## 4. Worker de vencimiento

- [x] 4.1 Implementar job periódico que vence órdenes sin acreditar y libera hueco; verificar test del job.

## 5. Agenda y reportes

- [x] 5.1 Exponer estado de cobro en agenda y reporte de señas pendientes; verificar endpoint de agenda incluye cobro.

## 6. Integración

- [x] 6.1 Prueba E2E del Flujo 1 con seña (reserva → pago → webhook → confirmado); verificar en entorno de test.
