# Spec Delta

## REMOVED Requirements

### Requirement: Cuenta corriente de solo deuda con saldo de lectura

**Reason**: C-15 habilita el cobro de saldo en mostrador; la cuenta corriente deja
de ser solo-débito y pasa a admitir créditos originados por pagos, manteniendo el
saldo derivado y los movimientos append-only.

**Migration**: Los débitos de presupuestos aceptados siguen creándose igual. Los
clientes que necesiten cobrar usan el nuevo registro de pagos; las lecturas de
saldo y movimientos mantienen el mismo contrato (`moneda`, `saldo`,
`movimientos`).

## ADDED Requirements

### Requirement: Cuenta corriente con saldo derivado y pagos append-only

El sistema SHALL exponer el saldo de la cuenta corriente como la suma algebraica de
sus movimientos (débitos menos créditos) y SHALL registrar pagos como créditos
nuevos, sin permitir editar ni borrar movimientos existentes.

#### Scenario: Saldo con débito y crédito

- **WHEN** un paciente tiene un débito de 18000,75 ARS y un pago de 8000,00 ARS
- **THEN** el saldo expuesto es 10000,75 ARS y ambos movimientos aparecen en la lista

#### Scenario: Saldo a favor

- **WHEN** el pago supera la deuda registrada
- **THEN** el saldo expuesto queda negativo por la diferencia y el movimiento de crédito permanece visible

#### Scenario: Movimiento inmutable

- **WHEN** se intenta editar o borrar un pago ya registrado por API o SQL directo
- **THEN** la operación falla y el movimiento original queda intacto

### Requirement: Pago de saldo idempotente

El sistema SHALL registrar un pago con monto mayor a cero y medio
`efectivo|transferencia|mp`, y SHALL devolver el mismo movimiento cuando recibe dos
veces la misma clave de idempotencia, sin duplicar el crédito.

#### Scenario: Pago válido

- **WHEN** recepción registra un pago de 15000,00 ARS en efectivo con una clave nueva
- **THEN** la cuenta corriente registra un crédito de 15000,00 ARS y el saldo baja en ese monto

#### Scenario: Reintento con la misma clave

- **WHEN** se repite el pago con la misma clave de idempotencia
- **THEN** el sistema devuelve el mismo movimiento y la cuenta conserva un solo crédito

#### Scenario: Claves distintas

- **WHEN** se registran dos pagos con claves de idempotencia diferentes
- **THEN** la cuenta corriente registra dos créditos y el saldo refleja ambos

#### Scenario: Monto inválido

- **WHEN** el pago informa monto cero o negativo
- **THEN** el sistema responde 422 y no registra el movimiento

#### Scenario: Medio inválido

- **WHEN** el pago informa un medio distinto de `efectivo`, `transferencia` o `mp`
- **THEN** el sistema responde 422 y no registra el movimiento

### Requirement: Recibo PDF del pago

El sistema SHALL generar un recibo PDF reproducible para cada pago con paciente,
monto, medio, fecha y referencia, y SHALL responder 404 cuando el movimiento no
pertenece al tenant de la sesión.

#### Scenario: Recibo del pago propio

- **WHEN** un usuario con permiso de cobros descarga el recibo de un pago de su tenant
- **THEN** recibe un PDF con el monto, el medio y la referencia del movimiento

#### Scenario: Recibo de otro tenant

- **WHEN** se solicita el recibo de un movimiento de otro tenant
- **THEN** el sistema responde 404 sin revelar su existencia

### Requirement: Roles de escritura y lectura de cobros

El sistema SHALL permitir registrar pagos solo a propietario y recepción, SHALL
permitir leer saldo, movimientos y recibos a propietario, recepción y odontólogo, y
SHALL denegar el acceso a asistente.

#### Scenario: Recepción cobra

- **WHEN** recepción registra un pago del paciente
- **THEN** la operación se permite y el saldo se actualiza

#### Scenario: Odontólogo consulta sin cobrar

- **WHEN** un odontólogo lee la cuenta corriente o un recibo
- **THEN** la lectura se permite, pero el registro de pagos responde 403

#### Scenario: Asistente sin permiso

- **WHEN** un asistente intenta leer la cuenta corriente o registrar un pago
- **THEN** el sistema responde 403
