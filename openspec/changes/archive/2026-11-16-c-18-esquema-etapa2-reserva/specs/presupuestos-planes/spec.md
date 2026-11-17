## ADDED Requirements

### Requirement: Reserva fiscal sin implementación en v1.0

La reserva de etapa 2 SHALL mantener `paciente.obra_social`, existente desde C-12, y añadir únicamente las tablas stub del nomenclador y comprobantes sin habilitar emisión fiscal.

#### Scenario: Migración de reserva

- **WHEN** se aplica la migración C-18
- **THEN** no se agrega otra vez `paciente.obra_social` y la facturación sigue deshabilitada
