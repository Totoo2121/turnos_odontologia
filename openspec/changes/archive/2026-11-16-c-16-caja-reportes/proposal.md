# Proposal

## Why

C-15 dejó caja diaria y cobros operativos, pero `/reportes` seguía siendo un placeholder y el dueño no podía revisar tendencias del consultorio. C-16 completa los reportes de US-040 usando turnos, señas acreditadas y el ledger de planes ya existentes.

## What Changes

- Agregar API tenant-scoped para ocupación en minutos, ausentismo/cancelaciones y recaudación por profesional.
- Reemplazar el placeholder web de reportes con filtros de fecha, tablas y totales ARS según alcance del rol.
- Reutilizar el reporte existente de señas pendientes y el cierre diario implementado en C-15.
- Declarar que no se calcula porcentaje de ocupación hasta que exista disponibilidad/jornada por profesional.

## Capabilities

### New Capabilities

- `reportes-operativos`: lecturas operativas y financieras por período con alcance por rol.

### Modified Capabilities

- `caja-mostrador`: separa reportes analíticos del cierre diario ya existente y limita las métricas financieras a propietario/odontólogo propio.

## Impact

- Backend `app/application/reportes.py`, `app/api/reportes.py` y wiring de `main.py`.
- Frontend `features/reportes` y ruta `/reportes`.
- Sin migración ni dependencias runtime nuevas; auditoría de consultas en C-17.
- Criterios para ocupación limitados a tiempo agendado porque no existe horario laboral persistido.
