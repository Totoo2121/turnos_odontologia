# Design

## Context

La paciente ya contiene `obra_social`; el MVP no implementa facturación, recetas, IA, perfiles externos ni integraciones de imagen.

## Goals / Non-Goals

**Goals:** reservar dos tablas mínimas bajo tenant/RLS, declarar la frontera de v1.0 y publicar respuestas 501 protegidas.

**Non-Goals:** conexión ARCA/AFIP, nomenclador real, liquidar OS, generar recetas, IA, perfil o API pública, radiología/laboratorio.

## Decisions

- La revisión 012 depende de C-17 revisión 011. `paciente.obra_social` permanece intacta porque fue creada por C-12.
- Las tablas stub solo contienen IDs tenant-scoped y estado reservado; su diseño completo requiere descubrimiento de integraciones.
- Cada ruta stub requiere rol propietario y responde 501; no se crea endpoint público sin rate-limit/firma.
- ADR-001 declara exclusiones de v1.0 y criterios de activación para futuras etapas.

## Risks / Trade-offs

Las columnas mínimas no deben confundirse con un contrato fiscal definitivo. La expansión requiere análisis tributario/regulatorio antes de almacenar comprobantes reales.
