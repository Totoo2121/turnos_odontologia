## ADDED Requirements

### Requirement: Reportes separados del cierre diario

La caja SHALL conservar el cierre diario existente y el área de reportes SHALL mostrar ocupación, ausentismo y recaudación de períodos mediante `reportes-operativos`, sin duplicar el cierre diario.

#### Scenario: Dueño abre reportes

- **WHEN** el propietario visita `/reportes`
- **THEN** puede filtrar fechas y ver métricas de operación y finanzas dentro de su tenant
