## Why

La ruta `/admin` todavía muestra un placeholder aunque el propietario necesita una entrada funcional para administrar el consultorio, el equipo y las capacidades existentes de auditoría y exportación. Esta pantalla también debe permitir mostrar el alcance real del MVP sin inventar integraciones de etapa 2.

## What Changes

- Reemplazar el placeholder por un panel de propietario con perfil de clínica editable, usuarios del tenant, auditoría consultable y exportación descargable.
- Añadir endpoints tenant-scoped para leer/actualizar perfil y listar/crear usuarios con roles permitidos y contraseña inicial segura.
- Reutilizar los endpoints existentes de auditoría y exportación; mantener visibilidad exclusiva del propietario.
- Conservar Admin como funcionalidad del MVP; no implementar billing, integraciones externas ni capacidades de etapa 2.

## Impact

- Affected code: `backend/app/api/admin.py`, frontend `pages/admin`, API/admin tests, router tests y documentación del change.
- Database: sin cambios de esquema; usa `tenant`, `usuario`, `rol` y `user_rol` existentes con RLS.
- Security: `propietario` únicamente; tenant derivado del JWT; credenciales nunca se devuelven en respuestas; cambios sensibles quedan auditados.
