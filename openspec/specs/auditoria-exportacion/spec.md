# auditoria-exportacion Specification

## Purpose
Dar trazabilidad append-only a eventos sensibles y permitir al propietario extraer los datos de su tenant en formato abierto, sin retener el paquete.

## Requirements

### Requirement: Eventos sensibles append-only

El sistema SHALL registrar acceso a HCE, cambios de agenda y cobros, consultas de reportes y ciclo de exportación. Eventos SHALL pertenecer a un tenant, ser append-only a nivel de base de datos y no contener cuerpos de request ni contenido clínico.

#### Scenario: Acceso a historia clínica

- **WHEN** una petición autenticada consulta o modifica un recurso HCE
- **THEN** queda evento con actor, recurso, método, ruta y fecha dentro del tenant correspondiente

#### Scenario: Intento de editar un evento

- **WHEN** una conexión ejecuta UPDATE, DELETE o TRUNCATE sobre `audit_evento`
- **THEN** PostgreSQL rechaza la operación

### Requirement: Consulta de auditoría restringida

La API SHALL permitir al propietario consultar eventos de su tenant con filtros temporales, de evento y paginación; SHALL denegar otros roles y tenant ajeno.

#### Scenario: Propietario consulta auditoría

- **WHEN** propietario pide los últimos eventos
- **THEN** recibe solo eventos del tenant de su JWT en orden descendente

### Requirement: Exportación completa temporal

La API SHALL encolar la exportación completa del tenant; el worker SHALL incluir tablas de dominio, audit trail y archivos clínicos disponibles en ZIP abierto. Credenciales y tokens SHALL quedar excluidos. El artefacto SHALL ser de descarga única y vencer a los 30 minutos.

#### Scenario: Exportación de un tenant

- **WHEN** el propietario solicita su exportación
- **THEN** el worker produce JSON y archivos de ese tenant sin filas de otros tenants

#### Scenario: Descarga única y vencimiento

- **WHEN** el propietario descarga el paquete o pasan 30 minutos
- **THEN** el archivo se elimina y queda evento de descarga auditado

### Requirement: Aislamiento de base

Las tablas `audit_evento` y `exportacion` SHALL usar RLS y FORCE RLS con el tenant de sesión.

#### Scenario: Consulta cruzada

- **WHEN** tenant A intenta leer exportación o auditoría de tenant B
- **THEN** PostgreSQL no devuelve sus filas
