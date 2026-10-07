# Flujos Principales

## Flujo 1: Reserva online con seña
**Disparador**: paciente abre `/reservar/{slug}`. **Actor**: paciente.
**Pasos**:
1. Frontend muestra prestaciones → profesionales habilitados → huecos válidos (API descuenta turnos, bloqueos).
2. Paciente elige horario, deja nombre + WhatsApp, acepta política de cancelación visible.
3. Si la prestación exige seña: API crea orden MP → paciente paga → webhook IPN acredita → turno `confirmado` (o `reservado` + recordatorios si no exige).
4. Sistema envía confirmación por WhatsApp + email con link de portal (token).
**Casos de error**:
- Hueco tomado en el ínterin → 409 + oferta de alternativas y lista de espera.
- Pago vencido/rechazado → reserva anulada y hueco liberado (RN-AD-04).

## Flujo 2: Confirmación y recordatorios automáticos
**Disparador**: cron del worker. **Actor**: sistema.
**Pasos**:
1. Worker detecta turnos en ventana T-48h/T-24h sin confirmar.
2. Envía plantilla WA (API oficial) + email respaldo; registra `recordatorio` enviado.
3. Paciente confirma por WA → estado `confirmado` + `confirmado_at` auditado.
4. Sin confirmación al umbral → hueco en riesgo + aviso a recepción; vencido → se ofrece a lista de espera.
**Casos de error**:
- Fallo BSP → reintento con backoff + fallback email + alerta operativa.

## Flujo 3: Atención con HCE y odontograma
**Disparador**: paciente en sala. **Actor**: odontólogo.
**Pasos**:
1. Odontólogo abre turno → HCE del paciente + odontograma actual.
2. Registra evolución (append-only) + eventos de piezas + adjunta RX/fotos.
3. Arma presupuesto sobre piezas → envía al paciente; si acepta → plan por etapas + deuda en cta. cte. + consentimiento a firmar.
4. Cierra turno como `atendido`; si corresponde, agenda control (recall futuro).
**Casos de error**:
- Paciente de otro profesional → denegado salvo propietario/derivación (RN-SE-02).

## Flujo 4: Cobro en mostrador y seña
**Disparador**: paciente paga. **Actor**: recepción.
**Pasos**:
1. Recepción ve deuda/turno con estado de cobro MP.
2. Cobra saldo (efectivo/transferencia/MP) → recibo + actualiza cuenta corriente.
3. Cierre de caja diario cuadra con turnos atendidos.
**Casos de error**:
- IPN duplicado de MP → idempotencia por `mp_payment_id`.

## Flujo 5: Cancelación y auto-relleno
**Disparador**: paciente cancela (portal/WA) o falta. **Actor**: paciente/sistema.
**Pasos**:
1. Cancela dentro del plazo → hueco libre; seña según política (devuelve/crédito).
2. Sistema ofrece el hueco a lista de espera por orden; primera aceptación lo ocupa.
3. Ausente → marca + recall a 7 días (RN-NO-03).
**Casos de error**:
- Cancelación fuera de plazo → registra y aplica política de seña visible.

## Flujo 6: Exportación de datos del tenant
**Disparador**: propietario la solicita. **Actor**: propietario.
**Pasos**:
1. Solicita exportación → worker genera paquete (pacientes, turnos, HCE, cobros) en formato abierto.
2. Descarga + evento de auditoría.
