# reportes-operativos Specification

## Purpose
Proveer al consultorio reportes seguros de agenda, ausentismo y recaudación, acotados por tenant, fechas y alcance del rol.

## Requirements

### Requirement: Ocupación y asistencia

El sistema SHALL mostrar turnos y minutos ocupados por profesional en un período, junto con atendidos, ausentes y cancelados. SHALL indicar el alcance del reporte según rol. No SHALL calcular porcentaje contra capacidad mientras no existan jornadas laborales persistidas.

#### Scenario: Dueño consulta agenda

- **WHEN** el propietario consulta el reporte de un período válido
- **THEN** ve turnos y minutos de todos los profesionales de su tenant, sin datos de otros tenants

#### Scenario: Odontólogo consulta solo sus turnos

- **WHEN** un odontólogo consulta ocupación
- **THEN** solo obtiene su profesional asociado y sus minutos agendados

### Requirement: Ausentismo

El sistema SHALL informar ausentes y cancelados por profesional y período; la tasa SHALL ser ausentes divididos por turnos del período, con cero cuando el período no tiene turnos.

#### Scenario: Período con ausencias

- **WHEN** hay dos ausencias sobre cinco turnos
- **THEN** el reporte muestra tasa 40% y mantiene cancelaciones en una cuenta separada

### Requirement: Recaudación y deuda de planes

El sistema SHALL mostrar señas acreditadas y créditos de cuenta corriente en ARS, recaudación atribuible por profesional y saldo actual de débitos netos de planes. SHALL restringir importes totales al propietario y limitar al odontólogo a cobros de turnos propios.

#### Scenario: Dueño consulta recaudación

- **WHEN** el propietario selecciona un período
- **THEN** ve señas acreditadas, cobros de cuenta, total por profesional y deuda neta de planes

#### Scenario: Recepción consulta finanzas

- **WHEN** recepción consulta reportes
- **THEN** puede ver operación y ausentismo, pero no importes de recaudación

### Requirement: Parámetros seguros

El sistema SHALL aceptar fechas inclusivas con un máximo de 367 días; SHALL rechazar rango invertido o mayor con 422 y SHALL aplicar tenant/RLS.

#### Scenario: Rango fuera de política

- **WHEN** se pide un período mayor a 367 días
- **THEN** la API responde 422 y no devuelve datos
