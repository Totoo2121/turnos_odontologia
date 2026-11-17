# reservas-etapa2 Specification

## Purpose
Reservar estructura multi-tenant mínima para capacidades post-MVP y responder de forma explícita que sus integraciones no están habilitadas en v1.0.

## Requirements

### Requirement: Esquema reservado aislado por tenant

La revisión 012 SHALL crear `nomenclador` y `comprobante_fiscal` vacías con tenant_id, claves e índices; ambas SHALL usar RLS y FORCE RLS. SHALL conservar `paciente.obra_social` existente sin una columna duplicada.

#### Scenario: Migración segura

- **WHEN** se aplica la revisión 012 sobre el head 011
- **THEN** aparecen ambas tablas con aislamiento tenant y la columna de obra social permanece única

### Requirement: Integraciones futuras deshabilitadas en v1.0

Las rutas reservadas para ARCA, liquidaciones de OS, ReNaPDiS, IA, perfil/API pública, radiología y laboratorio SHALL requerir propietario autenticado y responder HTTP 501 con mensaje de etapa.

#### Scenario: Integración no disponible

- **WHEN** propietario llama una ruta reservada
- **THEN** recibe 501 indicando que la capacidad se activa en etapa 2

#### Scenario: Rol sin autorización

- **WHEN** un rol distinto de propietario llama una ruta reservada
- **THEN** la API responde 403 sin ejecutar integración alguna
