# Proposal

## Why

C-18 prepara el esquema del siguiente ciclo sin abrir el alcance de v1.0. La base ya cuenta con `paciente.obra_social` desde C-12, pero aún faltan tablas reservadas y respuestas explícitas para integraciones futuras.

## What Changes

- Crear migración 012 con tablas tenant-scoped vacías `nomenclador` y `comprobante_fiscal`, RLS + FORCE RLS.
- No volver a crear `paciente.obra_social`.
- Añadir endpoints autenticados de etapa 2 que responden 501 y describen que no están disponibles en v1.0.
- Documentar decisión y condiciones para activar cada integración.

## Capabilities

### New Capabilities

- `reservas-etapa2`: esquema mínimo y stubs autenticados para FE ARCA, obras sociales, ReNaPDiS, IA, perfil/API pública, radiología y laboratorio.

### Modified Capabilities

- `presupuestos-planes`: aclara que `obra_social` se reservó en C-12 y que C-18 agrega solo las tablas restantes.

## Impact

- Backend: modelos y router de etapa 2.
- Base: Alembic 012 lineal después de C-17.
- Sin credenciales externas, lógica de negocio, endpoints públicos, emisión fiscal ni integraciones reales.
