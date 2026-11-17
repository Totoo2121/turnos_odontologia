# Spec Delta

## ADDED Requirements

### Requirement: API de creación de turno

El sistema SHALL exponer `POST /api/turnos` para propietario y recepción, calcular
`fin` en el servidor a partir de `prestacion.duracion_min + buffer`, validar que
profesional, sillón, prestación y paciente pertenezcan al tenant, y rechazar
solapamientos o bloqueos sin crear el turno.

#### Scenario: Turno creado con fin calculado

- **WHEN** recepción crea un turno de una prestación ficticia de 30 minutos con buffer 10
- **THEN** el turno se persiste en estado `pendiente` con `fin = inicio + 40 minutos`

#### Scenario: Solape rechazado

- **WHEN** el horario pedido se solapa con otro turno del profesional o del sillón
- **THEN** el sistema responde 409 y no crea el turno

#### Scenario: Bloqueo rechazado con motivo

- **WHEN** el horario pedido cae dentro de un bloqueo
- **THEN** el sistema responde 409 con el motivo del bloqueo y no crea el turno

#### Scenario: Referencia de otro tenant

- **WHEN** el pedido referencia un profesional, sillón, prestación o paciente de otro tenant
- **THEN** el sistema responde 422 o 404 y no crea el turno

#### Scenario: Rol sin permiso de creación

- **WHEN** un odontólogo o asistente intenta crear un turno
- **THEN** el sistema responde 403

### Requirement: API de cambio de estado del turno

El sistema SHALL exponer `PATCH /api/turnos/{id}/estado` para propietario,
recepción y odontólogo, permitiendo solo transiciones válidas, tratando `atendido`,
`ausente` y `cancelado` como estados finales y respondiendo 409 ante una transición
inválida.

#### Scenario: Cierre como atendido

- **WHEN** recepción o el odontólogo marca un turno `pendiente` o `confirmado` como `atendido`
- **THEN** el turno queda en `atendido` y refleja la fecha de actualización

#### Scenario: Transición inválida

- **WHEN** se intenta mover un turno `cancelado` a `atendido`
- **THEN** el sistema responde 409 y conserva el estado `cancelado`

#### Scenario: Repetición del mismo estado

- **WHEN** se envía el estado que el turno ya tiene
- **THEN** el sistema responde 200 con el turno sin cambios

#### Scenario: Turno de otro tenant

- **WHEN** se intenta cambiar el estado de un turno de otro tenant
- **THEN** el sistema responde 404 sin revelar su existencia

#### Scenario: Asistente sin permiso de cambio

- **WHEN** un asistente intenta cambiar el estado de un turno
- **THEN** el sistema responde 403

### Requirement: API de cancelación con política de seña

El sistema SHALL exponer `POST /api/turnos/{id}/cancelar`, liberar el hueco,
respetar la antelación mínima de la prestación e informar si la cancelación fue
tardía y si la seña se pierde según la política vigente.

#### Scenario: Cancelación en término

- **WHEN** recepción cancela un turno con antelación mayor o igual a la mínima de la prestación
- **THEN** el turno queda `cancelado` y la respuesta indica que la seña no se pierde

#### Scenario: Cancelación tardía

- **WHEN** se cancela un turno con menos antelación que la mínima
- **THEN** el turno queda `cancelado` y la respuesta indica cancelación tardía con la política de seña aplicada

#### Scenario: Cancelación repetida

- **WHEN** se vuelve a cancelar un turno ya cancelado
- **THEN** el sistema responde 200 con el mismo turno sin duplicar efectos

#### Scenario: Turno inexistente o ajeno

- **WHEN** se intenta cancelar un turno que no existe en el tenant de la sesión
- **THEN** el sistema responde 404
