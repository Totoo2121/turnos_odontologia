# core-multitenant Specification

## Purpose

Provee las entidades base multi-tenant y los patrones de acceso que garantizan aislamiento total por tenant para todo el dominio clínico y de agenda.

## Requirements

### Requirement: Identidad de tenant única y configurable

El sistema SHALL identificar cada organización por un `slug_reserva` único global, con `plan` y `moneda` (default ARS según RN-AD-01).

#### Scenario: Slug duplicado rechazado

- **WHEN** se intenta crear un segundo tenant con un `slug_reserva` ya existente
- **THEN** la operación falla con error de unicidad y no se crea ningún registro

#### Scenario: Moneda por defecto ARS

- **WHEN** se crea un tenant sin especificar `moneda`
- **THEN** el tenant queda con `moneda = ARS`

### Requirement: Aislamiento por tenant en toda query de dominio (RN-SE-01)

El sistema SHALL garantizar que toda lectura o escritura de dominio quede scopeada a un único `tenant_id`, de modo que ningún tenant vea ni modifique datos de otro.

#### Scenario: Query cruzada no devuelve datos ajenos

- **WHEN** un contexto del tenant A lista usuarios, sucursales o cualquier entidad de dominio
- **THEN** ningún registro del tenant B aparece en el resultado

#### Scenario: Acceso directo cruzado denegado

- **WHEN** un contexto del tenant A intenta leer o modificar un registro del tenant B por id
- **THEN** el sistema lo trata como inexistente o deniega la operación sin revelar su contenido

### Requirement: Enforcement de aislamiento a nivel base de datos

El sistema SHALL aplicar `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` en cada tabla de tenant, de modo que el aislamiento no dependa solo del `WHERE` de aplicación.

#### Scenario: Conexión sin contexto de tenant no lee filas ajenas

- **WHEN** una sesión DB sin `tenant_id` de aplicación intenta leer una tabla de tenant
- **THEN** no recibe filas (política por defecto deniega) salvo rol de servicio explícito (migraciones/seed)

#### Scenario: Políticas existen en Migración 001

- **WHEN** se inspecciona el esquema tras `alembic upgrade head`
- **THEN** cada tabla de tenant tiene RLS + FORCE RLS y al menos una política restrictiva documentada

### Requirement: Baja lógica uniforme vía AuditMixin

El sistema SHALL exponer `is_active`, `created_at`, `updated_at`, `deleted_at` en cada entidad de dominio, y toda baja SHALL ser soft-delete (marca `deleted_at` + `is_active=false`, nunca `DELETE` físico desde repositorios).

#### Scenario: Registro borrado desaparece del listado pero persiste

- **WHEN** se elimina un usuario o sucursal existente
- **THEN** ya no aparece en listados por defecto pero su fila persiste con `deleted_at` no nulo e `is_active=false`

#### Scenario: Updated_at avanza en cada modificación

- **WHEN** se modifica una entidad persistida
- **THEN** su `updated_at` queda posterior a su `created_at` y al valor previo

### Requirement: Repositorio genérico y unidad de trabajo atómica

El sistema SHALL proveer un `BaseRepository[T]` tenant-scopeado y una `UnitOfWork` que agrupa cambios multi-entidad en una transacción atómica (commit todo-o-nada con rollback ante fallo).

#### Scenario: CRUD genérico respeta tenant

- **WHEN** se crea, lee, actualiza y elimina una entidad vía repositorio con `tenant_id` A
- **THEN** todas las operaciones solo afectan filas del tenant A y el listado filtra por tenant

#### Scenario: Fallo multi-entidad revierte todo

- **WHEN** una unidad de trabajo con dos escrituras falla en la segunda (ej. unicidad violada)
- **THEN** ninguna de las dos escrituras persiste (rollback completo)

### Requirement: Seed mínimo idempotente con datos ficticios

El sistema SHALL proveer un seed que crea 1 tenant demo, los 4 roles (`propietario|odontologo|recepcion|asistente`) y 1 usuario ADMIN propietario, re-ejecutable sin duplicar y usando solo datos sintéticos marcados ficticios.

#### Scenario: Seed repetido no duplica

- **WHEN** el seed se ejecuta dos veces seguidas sobre la misma DB
- **THEN** sigue habiendo exactamente 1 tenant demo, 4 roles y 1 admin, sin error fatal

#### Scenario: Admin propietario pertenece al tenant demo

- **WHEN** se inspecciona el usuario ADMIN tras el seed
- **THEN** tiene `tenant_id` del tenant demo, está activo y posee el rol `propietario`

### Requirement: Migración 001 versionada y reversible

El sistema SHALL entregar la Migración Alembic 001 que crea `tenant`, `sucursal`, `usuario`, `rol`, `user_rol` sobre la baseline de C-01, aplicable en una DB vacía y reversible sin dejar residuos.

#### Scenario: Upgrade sobre baseline crea las 5 tablas

- **WHEN** se ejecuta `alembic upgrade head` sobre una DB con solo la baseline aplicada
- **THEN** existen las 5 tablas con PKs, FKs indexadas y constraints, y `alembic current` muestra la revisión 001

#### Scenario: Downgrade elimina lo creado

- **WHEN** se ejecuta `alembic downgrade -1` desde 001
- **THEN** las 5 tablas y sus políticas RLS desaparecen y la baseline sigue válida
