# Spec Delta

## Purpose

Da a recepción una caja de mostrador donde ver la deuda del paciente, cobrar el
saldo en efectivo, transferencia o Mercado Pago, emitir un recibo y cerrar el día
contra los turnos atendidos.

## ADDED Requirements

### Requirement: Deuda y movimientos visibles en la caja

La app SHALL permitir buscar un paciente y mostrar el saldo en ARS y sus
movimientos de cuenta corriente con tipo, monto, fecha y referencia; SHALL mostrar
saldo 0 y lista vacía cuando el paciente no tiene cuenta.

#### Scenario: Paciente con deuda

- **WHEN** recepción abre la caja de un paciente con un débito aceptado
- **THEN** ve el saldo exacto en ARS y el movimiento con su referencia al presupuesto

#### Scenario: Paciente sin cuenta

- **WHEN** recepción abre la caja de un paciente sin movimientos
- **THEN** ve saldo 0,00 ARS y el estado vacío de movimientos

#### Scenario: Asistente sin acceso a caja

- **WHEN** un asistente intenta abrir la caja
- **THEN** la app lo redirige a la pantalla de acceso denegado y no consulta la cuenta corriente

### Requirement: Cobro de saldo con medio de pago

La app SHALL registrar un pago del paciente con monto mayor a cero y medio
`efectivo`, `transferencia` o `mp`, SHALL actualizar el saldo visible y SHALL
rechazar el cobro para roles sin permiso de escritura de cobros.

#### Scenario: Cobro en efectivo

- **WHEN** recepción cobra 15000,00 ARS en efectivo
- **THEN** la API registra el crédito, el saldo baja en 15000,00 ARS y la caja muestra el pago en la lista de movimientos

#### Scenario: Cobro por transferencia o Mercado Pago

- **WHEN** recepción elige transferencia o Mercado Pago como medio
- **THEN** el pago se registra con ese medio en su referencia y el recibo lo indica

#### Scenario: Monto inválido

- **WHEN** recepción intenta cobrar un monto cero o negativo
- **THEN** la app muestra el error 422 y no registra el movimiento

#### Scenario: Odontólogo intenta cobrar

- **WHEN** un odontólogo intenta registrar un pago
- **THEN** la API responde 403 y la app no ofrece la acción de cobro

### Requirement: Cobro idempotente ante reintentos

La app SHALL enviar una clave de idempotencia por intento de cobro y SHALL mostrar
el mismo movimiento cuando la API recibe la misma clave dos veces, sin duplicar la
deuda ni el recibo.

#### Scenario: Reintento del mismo cobro

- **WHEN** se repite un cobro con la misma clave de idempotencia
- **THEN** la cuenta corriente conserva un solo crédito y la caja muestra el mismo identificador de movimiento

#### Scenario: Cobros distintos con claves distintas

- **WHEN** recepción registra dos cobros con claves diferentes
- **THEN** la cuenta corriente suma dos créditos y el saldo refleja ambos

### Requirement: Recibo del pago

La app SHALL permitir descargar el recibo PDF de un pago con paciente, monto,
medio, fecha y referencia, y SHALL responder 404 cuando el movimiento no pertenece
al tenant de la sesión.

#### Scenario: Descarga del recibo

- **WHEN** recepción descarga el recibo de un pago recién registrado
- **THEN** obtiene un PDF con el monto y el medio del pago

#### Scenario: Recibo de otro tenant

- **WHEN** un usuario intenta descargar el recibo de un movimiento de otro tenant
- **THEN** el backend responde 404 y la app no muestra datos del movimiento

### Requirement: Cierre de caja diario contra turnos atendidos

La app SHALL mostrar el cierre de caja de una fecha con el total cobrado por medio,
la cantidad de pagos, la deuda generada, los turnos atendidos del día y el detalle
de movimientos, y SHALL señalar la diferencia de caja entre lo cobrado y la deuda
generada junto con la cantidad de turnos atendidos.

#### Scenario: Cierre con cobros y turnos

- **WHEN** recepción abre el cierre del día con dos pagos, deuda generada y tres turnos atendidos
- **THEN** ve el total por medio, la cantidad de pagos, la deuda generada, la diferencia de caja y los tres turnos atendidos

#### Scenario: Día sin movimientos

- **WHEN** recepción abre el cierre de un día sin pagos ni turnos atendidos
- **THEN** ve totales en cero y los estados vacíos correspondientes

#### Scenario: Rol sin permiso de caja

- **WHEN** un asistente intenta consultar el cierre de caja
- **THEN** la API responde 403 y la app no muestra totales

### Requirement: Cobro desde el turno del día

La app SHALL listar los turnos del día con su estado de agenda y su estado de cobro
de Mercado Pago, y SHALL permitir iniciar el cobro del saldo del paciente desde el
turno seleccionado.

#### Scenario: Turno con seña acreditada

- **WHEN** recepción selecciona un turno cuyo cobro de Mercado Pago figura `acreditado`
- **THEN** la caja muestra ese estado y permite cobrar el saldo pendiente del paciente

#### Scenario: Turno sin seña

- **WHEN** recepción selecciona un turno sin seña obligatoria
- **THEN** la caja muestra el estado `sin-sena` y el saldo del paciente
