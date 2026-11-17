# agenda-mostrador Specification

## Purpose
Agenda del mostrador: UI para que recepción y roles autorizados visualicen y operen la agenda diaria/semanal por profesional y por sillón, creen turnos solo en huecos válidos, ejecuten el ciclo de estados y creen sobreturnos autorizados.

## Requirements

### Requirement: Vista día y semana por profesional y sillón
El sistema SHALL mostrar la agenda en vistas día y semana, filtrables por profesional o por sillón, con estados y estado de cobro visibles en cada turno.

#### Scenario: Render de vista día
- **WHEN** recepcionista abre la agenda en vista día
- **THEN** se muestran los turnos del día agrupados por profesional/sillón con estado y cobro visible

#### Scenario: Cambio a vista semana
- **WHEN** el usuario cambia a vista semana
- **THEN** se muestran los 7 días con turnos y huecos disponibles

### Requirement: Creación de turno solo en hueco válido
El sistema SHALL permitir crear un turno únicamente sobre un hueco válido; al intentar crear sobre solape o bloqueo, SHALL rechazar con mensaje y motivo.

#### Scenario: Creación en hueco válido
- **WHEN** recepcionista selecciona un hueco libre y confirma
- **THEN** se crea el turno y aparece en la agenda

#### Scenario: Rechazo por solape
- **WHEN** se intenta crear un turno sobre un hueco ocupado
- **THEN** el sistema rechaza con mensaje indicando solape

#### Scenario: Rechazo por bloqueo
- **WHEN** se intenta crear un turno sobre un bloqueo
- **THEN** el sistema rechaza con mensaje indicando el motivo del bloqueo

### Requirement: Ciclo de estados de turno
El sistema SHALL permitir ejecutar confirmar, en-sala, atender, cancelar, reprogramar y marcar ausente contra los endpoints de C-06, respetando permisos por rol.

#### Scenario: Confirmar turno
- **WHEN** recepcionista confirma un turno reservado
- **THEN** el estado cambia a confirmado y se refleja en la agenda

#### Scenario: Cancelar turno
- **WHEN** recepcionista cancela un turno dentro de la antelación permitida
- **THEN** el turno pasa a cancelado y el hueco queda disponible

### Requirement: Sobreturno autorizado
El sistema SHALL permitir crear sobreturnos solo en prestaciones habilitadas y con rol autorizado, marcados visiblemente como sobreturno.

#### Scenario: Sobreturno permitido
- **WHEN** recepcionista crea sobreturno en prestación habilitada
- **THEN** se crea el turno marcado como sobreturno fuera de la grilla

#### Scenario: Sobreturno denegado por rol
- **WHEN** un rol no autorizado intenta crear sobreturno
- **THEN** el sistema deniega la acción

### Requirement: Guards por rol
El sistema SHALL restringir el acceso a la agenda según la matriz de roles: recepción y superiores operan; odontólogo ve su agenda; asistente según permisos.

#### Scenario: Acceso denegado a rol sin permiso
- **WHEN** un usuario sin permiso accede a la agenda
- **THEN** el sistema redirige o muestra acceso denegado
