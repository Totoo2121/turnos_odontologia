# ADR-001: Frontera de v1.0 y activación de Etapa 2

- **Estado:** aceptado para reserva de esquema; activación futura pendiente de change aprobado.
- **Fecha:** 2026-11-16.

## Decisión

v1.0 termina con caja/reportes, auditoría/exportación y una reserva mínima de esquema. No incluye integraciones ARCA, obras sociales/prepagas, ReNaPDiS, IA, perfil público, API pública, radiología ni laboratorio. Las rutas protegidas responden 501 hasta que cada integración tenga propuesta y change propios.

`paciente.obra_social` ya existe desde C-12; la migración 012 agrega solo `nomenclador` y `comprobante_fiscal` vacías, ambas aisladas con RLS + FORCE RLS. El stub fiscal no constituye un modelo tributario aprobado.

## Activación

Cada integración futura requiere: responsable funcional, revisión legal/regulatoria aplicable, proveedor oficial y credenciales de entorno, contrato de datos, estrategia de firma/idempotencia, pruebas de aislamiento y un change OpenSpec que sustituya el 501.

## Consecuencias

- No se emiten comprobantes ni recetas y no se envían datos a vendors.
- Los tenants no pueden usar tablas de otros tenants.
- Las tablas mínimas deberán evolucionar mediante migraciones Alembic numeradas, nunca DDL ad-hoc.
