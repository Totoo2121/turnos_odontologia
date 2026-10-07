# agenda-catalog Specification

## Purpose

Permite al propietario configurar la oferta real de la agenda — quién atiende, en qué sillón, qué prestación con qué duración y cuándo no hay disponibilidad — para que los turnos y el turnero online operen sobre huecos válidos.

## Requirements

### Requirement: Profesionales gestionables con prestaciones habilitadas

El sistema SHALL permitir CRUD de `Profesional` por tenant con `nombre`, `matricula?`, `especialidades[]`, `duracion_default_min` y lista de prestaciones habilitadas, exigiendo al menos una prestación habilitada para que sea agendable.

#### Scenario: Alta de profesional con habilitaciones

- **WHEN** un propietario crea un profesional con nombre, especialidades y dos prestaciones habilitadas de su tenant
- **THEN** responde 201 y el profesional queda agendable solo en esas prestaciones

#### Scenario: Profesional sin prestaciones no es agendable

- **WHEN** se intenta dejar un profesional sin ninguna prestación habilitada
- **THEN** responde 422 y el profesional sigue no agendable hasta habilitar al menos una

#### Scenario: Aislamiento por tenant en profesionales

- **WHEN** un token del tenant A pide un profesional del tenant B por id
- **THEN** responde 404 sin revelar sus datos

### Requirement: Sillón como recurso de primera clase asignable

El sistema SHALL permitir CRUD de `Sillon` por tenant con `nombre`, `sucursal_id?` y `activo`, de modo que todo turno futuro referencia exactamente un sillón.

#### Scenario: Alta de sillón Box 1

- **WHEN** un propietario crea el sillón "Box 1" activo en su tenant
- **THEN** responde 201 y el sillón queda disponible para asignar a turnos

#### Scenario: Sillón inactivo no se ofrece

- **WHEN** un sillón se marca `activo=false`
- **THEN** el generador de huecos y la creación de turnos lo excluyen hasta reactivarlo

### Requirement: Prestaciones configurables con validación de negocio

El sistema SHALL permitir CRUD de `Prestacion` por tenant con `nombre`, `duracion_min > 0`, `buffer_min >= 0`, `requiere_sillon`, `permite_sobreturno`, `seña_obligatoria`, `monto_seña`, `anticipacion_min_cancel_hs` y `precio` en ARS.

#### Scenario: Alta de prestación válida

- **WHEN** un propietario crea "Limpieza" con `duracion_min=45`, buffer 10, precio ARS y antelación 24h
- **THEN** responde 201 con todos los parámetros persistidos

#### Scenario: Duración no positiva rechazada

- **WHEN** se crea o edita una prestación con `duracion_min <= 0`
- **THEN** responde 422 y no persiste el cambio

#### Scenario: Seña obligatoria exige monto

- **WHEN** se crea una prestación con `seña_obligatoria=true` sin `monto_seña` positivo
- **THEN** responde 422 indicando el monto faltante

### Requirement: Cambio de duración no altera turnos ya creados (RN-AG-03)

El sistema SHALL congelar la duración efectiva en cada turno al crearlo, de modo que cambios posteriores de `prestacion.duracion_min` o buffer solo afectan turnos futuros.

#### Scenario: Edición de duración no reescribe historial

- **WHEN** se cambia `duracion_min` de 30 a 45 en una prestación con turnos ya creados
- **THEN** los turnos existentes conservan su `fin` original y solo los turnos nuevos usan 45 más buffer

### Requirement: Bloqueos con motivo impiden oferta y creación (RN-AG-05)

El sistema SHALL permitir CRUD de `Bloqueo` por tenant con `inicio`, `fin > inicio`, `motivo` y al menos un objetivo (`profesional_id?`/`sillon_id?`), y SHALL rechazar con el motivo cualquier hueco o turno dentro de su rango.

#### Scenario: Bloqueo por feriado descuenta huecos

- **WHEN** existe un bloqueo del profesional demo el 25/12 con motivo `feriado`
- **THEN** el generador de huecos no ofrece ningún slot que se solape con ese rango

#### Scenario: Bloqueo sin objetivo rechazado

- **WHEN** se crea un bloqueo sin `profesional_id` ni `sillon_id`
- **THEN** responde 422 porque el bloqueo debe apuntar a al menos un recurso

#### Scenario: Turno dentro de bloqueo rechazado con motivo

- **WHEN** se intenta crear o mover un turno a un rango cubierto por un bloqueo (flujo validado en C-06, aquí contrato de catálogo)
- **THEN** el sistema lo rechaza indicando el `motivo` del bloqueo

### Requirement: Generador de huecos sobre grilla con descuentos (RN-AG-04)

El sistema SHALL generar huecos candidatos en múltiplos de (`duracion_min + buffer`) de la prestación sobre la disponibilidad del profesional, descontando turnos existentes y bloqueos aplicables.

#### Scenario: Huecos descuentan turno y bloqueo

- **WHEN** se piden huecos de "Consulta 30'" para un día con un turno de 10:00–10:30 y un bloqueo de 12:00–13:00
- **THEN** la lista omite 10:00 y todo slot solapado con el bloqueo y ofrece el resto en múltiplos de 30 desde el inicio de jornada

#### Scenario: Prestación con buffer desplaza la grilla

- **WHEN** se piden huecos de "Limpieza 45'+10 buffer" desde las 09:00 libre
- **THEN** los huecos son 09:00, 09:55, 10:50 (paso 55) y ninguno se solapa con el siguiente

### Requirement: Autorización y aislamiento del catálogo

El sistema SHALL derivar `tenant_id` del JWT (nunca de parámetros), aplicar RLS + FORCE RLS y soft-delete en las 5 tablas, y autorizar por matriz: escritura solo `propietario`, lectura `propietario|odontologo|recepcion|asistente` según recurso.

#### Scenario: Recepción no escribe catálogo

- **WHEN** un usuario `recepcion` intenta crear una prestación
- **THEN** responde 403 sin efecto lateral, pero puede leer el catálogo (200)

#### Scenario: Baja es lógica y reversible

- **WHEN** un propietario elimina una prestación
- **THEN** no hay `DELETE` físico: queda `is_active=false` + `deleted_at` y deja de ofrecerse sin romper turnos históricos

### Requirement: Seed de catálogo idempotente con datos ficticios

El sistema SHALL proveer un seed re-ejecutable que crea las 5 prestaciones ejemplo, 1 sillón "Box 1", 1 profesional demo habilitado y feriados AR del año como bloqueos, usando solo datos sintéticos ficticios.

#### Scenario: Seed doble no duplica

- **WHEN** el seed de catálogo se ejecuta dos veces sobre el mismo tenant demo
- **THEN** la segunda ejecución no crea duplicados y el catálogo queda con 5 prestaciones, 1 sillón y 1 profesional demo
