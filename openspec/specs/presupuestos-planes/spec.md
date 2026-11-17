# presupuestos-planes Specification

## Purpose
Permite presupuestar tratamientos sobre las piezas del odontograma, convertir la aceptación en un plan por etapas y registrar la deuda exacta en la cuenta corriente del paciente.

## Requirements

### Requirement: Presupuesto en ARS sobre piezas del odontograma

El sistema SHALL crear presupuestos en ARS asociados a un paciente e historia clínica del tenant, con ítems que referencian una prestación y, opcionalmente, una pieza FDI y superficie válidas (RN-AD-01, RN-HC-03).

#### Scenario: Alta válida

- **WHEN** un odontólogo con acceso clínico crea un presupuesto con dos ítems, uno de ellos con pieza `16` y superficie `oclusal`
- **THEN** el sistema persiste el presupuesto en estado `borrador`, moneda `ARS` y ambos ítems con su pieza y superficie

#### Scenario: Moneda distinta de ARS

- **WHEN** el pedido intenta crear un presupuesto en otra moneda
- **THEN** el sistema responde 422 y no crea el presupuesto

#### Scenario: Pieza FDI inválida

- **WHEN** un ítem referencia una pieza fuera del rango FDI 11–48
- **THEN** el sistema responde 422 y no persiste el presupuesto ni el ítem

#### Scenario: Pieza de otro paciente

- **WHEN** se intenta presupuestar una pieza sobre una historia clínica que no pertenece al paciente indicado
- **THEN** el sistema responde 422 y no crea el presupuesto

### Requirement: Precio y descripción snapshot por ítem

El sistema SHALL fijar el precio unitario y la descripción de cada ítem al crearlo, tomando el precio de la prestación cuando el pedido no lo indique, y SHALL rechazar el alta cuando no haya precio disponible.

#### Scenario: Precio heredado del catálogo

- **WHEN** se agrega un ítem sin precio explícito y la prestación tiene precio
- **THEN** el ítem guarda ese precio como precio unitario y la descripción de la prestación

#### Scenario: Precio manual

- **WHEN** se agrega un ítem con precio explícito y la prestación no tiene precio
- **THEN** el ítem se crea con el precio enviado

#### Scenario: Sin precio disponible

- **WHEN** se agrega un ítem sin precio explícito y la prestación no tiene precio
- **THEN** el sistema responde 422 y no agrega el ítem

#### Scenario: Cambio posterior del catálogo

- **WHEN** la prestación cambia de precio después de creado el ítem
- **THEN** el ítem conserva el precio y la descripción que tenía al crearse

### Requirement: Total e importes exactos en ARS

El sistema SHALL calcular el importe de cada ítem como cantidad por precio unitario y el total del presupuesto como la suma de sus importes, con dos decimales y redondeo half-up.

#### Scenario: Total exacto

- **WHEN** un presupuesto tiene dos ítems de 15000,50 ARS y 3000,25 ARS
- **THEN** el total expuesto es 18000,75 ARS

#### Scenario: Recalculo al editar

- **WHEN** se agrega, edita o quita un ítem en estado `borrador`
- **THEN** el total del presupuesto se recalcula con los ítems vigentes

#### Scenario: Monto negativo

- **WHEN** un ítem o su cantidad se envía con valor negativo o cero
- **THEN** el sistema responde 422 y no modifica el presupuesto

### Requirement: Transiciones válidas del presupuesto

El sistema SHALL permitir solo las transiciones `borrador→enviado`, `enviado→aceptado` y `enviado→rechazado`, y SHALL rechazar con 409 cualquier otra transición.

#### Scenario: Envío

- **WHEN** un presupuesto en `borrador` con al menos un ítem se envía
- **THEN** pasa a `enviado` y registra la fecha de envío

#### Scenario: Transición inválida

- **WHEN** se intenta aceptar un presupuesto en `borrador`, o enviar uno ya `aceptado` o `rechazado`
- **THEN** el sistema responde 409 y conserva el estado original

#### Scenario: Aceptación posterior al envío

- **WHEN** se acepta un presupuesto en `enviado`
- **THEN** pasa a `aceptado` y registra la fecha de aceptación

#### Scenario: Rechazo posterior al envío

- **WHEN** se rechaza un presupuesto en `enviado`
- **THEN** pasa a `rechazado`, registra la fecha de rechazo y no genera plan ni deuda

### Requirement: Edición limitada al borrador

El sistema SHALL permitir editar ítems, validez y datos del presupuesto solo en estado `borrador`, y SHALL rechazar con 409 toda modificación o borrado después de enviado.

#### Scenario: Edición en borrador

- **WHEN** se modifica un ítem de un presupuesto en `borrador`
- **THEN** el cambio se persiste y el total se recalcula

#### Scenario: Edición tras el envío

- **WHEN** se intenta modificar un presupuesto o un ítem en estado `enviado`, `aceptado` o `rechazado`
- **THEN** el sistema responde 409 y no altera el contenido

#### Scenario: Borrado de un presupuesto aceptado

- **WHEN** se intenta borrar un presupuesto aceptado
- **THEN** el sistema responde 409 y conserva el presupuesto, su plan y su deuda

### Requirement: Validez del presupuesto

El sistema SHALL asignar una fecha de validez por defecto y SHALL rechazar con 409 la aceptación de un presupuesto cuya `validez_hasta` ya pasó.

#### Scenario: Validez por defecto

- **WHEN** se crea un presupuesto sin indicar `validez_hasta`
- **THEN** el sistema le asigna la fecha por defecto configurada

#### Scenario: Aceptación vencida

- **WHEN** se intenta aceptar un presupuesto enviado cuya validez terminó
- **THEN** el sistema responde 409, lo deja en `enviado` y no genera plan ni deuda

### Requirement: Aceptación genera plan por etapas

El sistema SHALL generar al aceptar un plan de tratamiento único con los ítems del presupuesto agrupados por la etapa declarada, el total aceptado y la etapa actual en la primera.

#### Scenario: Plan con etapas

- **WHEN** se acepta un presupuesto cuyos ítems declaran etapas 1, 2 y 2
- **THEN** el plan expone tres etapas con dos ítems en la etapa 2 y la etapa actual en 1

#### Scenario: Presupuesto sin ítems

- **WHEN** se intenta enviar o aceptar un presupuesto sin ítems
- **THEN** el sistema responde 422 y no cambia de estado

#### Scenario: Etapa inválida

- **WHEN** un ítem declara una etapa menor a 1 o mayor al máximo permitido
- **THEN** el sistema responde 422 y no persiste el ítem

### Requirement: Aceptación genera deuda exacta en cuenta corriente

El sistema SHALL registrar en la cuenta corriente del paciente un movimiento débito por el total aceptado, referenciado al presupuesto, y SHALL crear la cuenta si no existe.

#### Scenario: Deuda generada

- **WHEN** se acepta un presupuesto con total 18000,75 ARS
- **THEN** la cuenta corriente del paciente registra un débito de 18000,75 ARS y el saldo resultante es 18000,75 ARS

#### Scenario: Cuenta inexistente

- **WHEN** el paciente todavía no tiene cuenta corriente
- **THEN** el sistema la crea de forma idempotente y registra el débito una sola vez

#### Scenario: Saldo de otro paciente

- **WHEN** se acepta un presupuesto
- **THEN** el débito se registra solo en la cuenta del paciente del presupuesto

### Requirement: Aceptación idempotente

El sistema SHALL devolver el mismo plan y el mismo movimiento de deuda cuando la aceptación de un presupuesto ya aceptado se repite, sin duplicar ninguno de los dos.

#### Scenario: Repetición de la aceptación

- **WHEN** se vuelve a llamar la aceptación de un presupuesto ya aceptado
- **THEN** el sistema responde con el plan existente y la cuenta corriente conserva un solo débito por ese presupuesto

#### Scenario: Reintento concurrente

- **WHEN** dos aceptaciones del mismo presupuesto compiten
- **THEN** la unicidad por presupuesto y por referencia deja un solo plan y un solo débito

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

### Requirement: Movimientos de cuenta corriente append-only

El sistema SHALL impedir la edición y el borrado de movimientos de cuenta corriente, tanto por API como por base de datos.

#### Scenario: Corrección de un movimiento

- **WHEN** se necesita corregir un movimiento
- **THEN** se registra un movimiento nuevo y el anterior permanece inmutable

#### Scenario: Intento de escritura destructiva

- **WHEN** se intenta actualizar o borrar un movimiento por API o por SQL directo
- **THEN** la operación falla y el movimiento original queda intacto

### Requirement: Consentimiento exigible en planes invasivos

El sistema SHALL exigir un consentimiento invasivo firmado del paciente cuando al menos un ítem requiere consentimiento, y SHALL rechazar con 409 la aceptación sin generar plan ni deuda (RN-HC-04).

#### Scenario: Plan invasivo con consentimiento

- **WHEN** se acepta un presupuesto con un ítem que requiere consentimiento y el paciente tiene un consentimiento invasivo firmado
- **THEN** el sistema genera el plan y la deuda, y el plan referencia el consentimiento

#### Scenario: Plan invasivo sin consentimiento

- **WHEN** se acepta un presupuesto con un ítem que requiere consentimiento y el paciente no tiene consentimiento invasivo firmado
- **THEN** el sistema responde 409, deja el presupuesto en `enviado` y no genera plan ni deuda

#### Scenario: Plan no invasivo

- **WHEN** se acepta un presupuesto sin ítems que requieran consentimiento
- **THEN** el sistema genera el plan y la deuda sin exigir consentimiento

### Requirement: Visibilidad clínica y roles del presupuesto y la cuenta

El sistema SHALL restringir presupuestos y planes a propietario y odontólogo con acceso clínico al paciente, y SHALL permitir leer la cuenta corriente a los roles habilitados para cobros (RN-SE-02, RN-SE-03).

#### Scenario: Profesional tratante

- **WHEN** un odontólogo con turno o derivación del paciente crea y lee un presupuesto
- **THEN** la operación se permite

#### Scenario: Profesional ajeno

- **WHEN** un odontólogo sin turno ni derivación intenta leer o crear un presupuesto del paciente
- **THEN** el sistema responde 403 sin revelar datos clínicos

#### Scenario: Recepción no edita presupuestos

- **WHEN** recepción intenta crear, editar o aceptar un presupuesto
- **THEN** el sistema responde 403

#### Scenario: Recepción consulta la deuda

- **WHEN** recepción consulta la cuenta corriente de un paciente
- **THEN** el sistema devuelve el saldo y sus movimientos

#### Scenario: Asistente sin permiso de cobros

- **WHEN** un asistente intenta consultar la cuenta corriente
- **THEN** el sistema responde 403

### Requirement: Aislamiento multi-tenant de presupuestos, planes y cuenta corriente

El sistema SHALL aplicar RLS + FORCE RLS en las cinco tablas nuevas y SHALL responder 404 ante recursos de otro tenant.

#### Scenario: Lectura cruzada

- **WHEN** un usuario del tenant A solicita un presupuesto, plan o cuenta corriente del tenant B
- **THEN** el sistema responde 404 sin revelar su existencia

#### Scenario: RLS sin GUC

- **WHEN** una sesión de base de datos consulta las tablas nuevas sin `app.tenant_id` fijado
- **THEN** la política falla cerrada y no devuelve filas de ningún tenant

### Requirement: Autoría y moneda tomadas del servidor

El sistema SHALL tomar el autor del presupuesto desde el `sub` del token, SHALL ignorar cualquier autor enviado en el cuerpo y SHALL fijar la moneda en ARS.

#### Scenario: Autor explícito en el body

- **WHEN** el cuerpo incluye un autor distinto al del token
- **THEN** el sistema ignora ese valor y persiste el usuario autenticado

#### Scenario: Token sin identificador válido

- **WHEN** el `sub` del token no es un UUID
- **THEN** el sistema rechaza la escritura con 422

#### Scenario: Moneda impuesta por el servidor

- **WHEN** se lee o se crea un presupuesto
- **THEN** la moneda expuesta es siempre `ARS`, independientemente de lo enviado

### Requirement: Reserva fiscal sin implementación en v1.0

La reserva de etapa 2 SHALL mantener `paciente.obra_social`, existente desde C-12, y añadir únicamente las tablas stub del nomenclador y comprobantes sin habilitar emisión fiscal.

#### Scenario: Migración de reserva

- **WHEN** se aplica la migración C-18
- **THEN** no se agrega otra vez `paciente.obra_social` y la facturación sigue deshabilitada
