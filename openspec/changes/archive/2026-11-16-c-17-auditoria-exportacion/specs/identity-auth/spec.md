## ADDED Requirements

### Requirement: Registro de operaciones sensibles autenticadas

Las rutas autenticadas de HCE, agenda, cobros y reportes SHALL escribir un evento de auditoría append-only tras validar una identidad y tenant válidos, sin persistir datos de request ni contenido clínico.

#### Scenario: Cambio autenticado de agenda

- **WHEN** un usuario autenticado cambia un turno
- **THEN** el tenant ve un evento con actor, método, recurso y ruta
