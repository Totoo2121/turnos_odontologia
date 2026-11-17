# Spec Delta

## ADDED Requirements

### Requirement: Prestación declara requisito de consentimiento informado

El sistema SHALL permitir marcar una prestación como requeridora de consentimiento informado, con default `false`, y SHALL exponer ese valor al crear, editar y leer prestaciones.

#### Scenario: Default no invasiva

- **WHEN** se crea una prestación sin indicar el requisito de consentimiento
- **THEN** el sistema la persiste con `requiere_consentimiento=false`

#### Scenario: Prestación invasiva

- **WHEN** un propietario crea o edita una prestación con `requiere_consentimiento=true`
- **THEN** el sistema persiste el valor y lo devuelve en la lectura del catálogo

#### Scenario: Edición no invasiva

- **WHEN** se edita una prestación para volver `requiere_consentimiento` a `false`
- **THEN** el cambio se persiste y afecta solo a los ítems de presupuesto creados después
