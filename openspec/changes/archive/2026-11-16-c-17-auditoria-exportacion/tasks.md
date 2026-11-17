# Tasks

## 1. Persistencia inmutable y auditoría

- [x] 1.1 Crear modelos y migración 011 para auditoría y exportaciones con RLS + FORCE; verificar SQL offline, policies y cadena Alembic.
- [x] 1.2 Registrar eventos por API autenticada sin payload/PII y con prueba de inmutabilidad; verificar lectura clínica, cambio agenda y cobro.
- [x] 1.3 Agregar consulta owner-only con filtros y paginación; verificar rol y scoping tenant.

## 2. Exportación asíncrona

- [x] 2.1 Encolar exportación, serializar todas las tablas tenant-scoped y adjuntos; verificar secretos omitidos y tenant cruzado excluido.
- [x] 2.2 Exponer estado y descarga única con vencimiento de 30 min; verificar evento de descarga, expiración y eliminación de artefacto.
- [x] 2.3 Agregar tareas Celery idempotentes y manejo de error de worker/storage; verificar cola y resultados.

## 3. Integración

- [x] 3.1 Ejecutar backend tests, validación OpenSpec y migraciones offline; verificar todo el dominio de tenant en ZIP.
