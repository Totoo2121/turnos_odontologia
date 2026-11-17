## 1. API segura de administración
- [x] 1.1 Implementar lectura/edición de perfil tenant (solo nombre/moneda), validaciones y auditoría.
- [x] 1.2 Implementar listado y alta de usuarios tenant-scoped, roles permitidos, hash Argon2id y errores de conflicto/validación.
- [x] 1.3 Añadir pruebas de permisos, aislamiento, validación, hash y persistencia sin exponer secretos (5 pruebas API y 1 regresión de auditoría).

## 2. Panel frontend
- [x] 2.1 Reemplazar AdminPlaceholder por panel responsive de perfil, usuarios, auditoría y exportaciones.
- [x] 2.2 Añadir formularios de perfil/alta de usuario, consulta/filtrado de auditoría y estados de exportación/descarga.
- [x] 2.3 Actualizar pruebas de página/router con permisos, acciones y estados de error/vacío.

## 3. Cierre
- [x] 3.1 Suite backend: 655 passed, 19 skipped; suite frontend: 109 passed; build TypeScript/Vite correcto; Ruff y Black aprobados.
- [x] 3.2 Change validado, roadmap actualizado y C-21 archivado.
