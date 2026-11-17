## Context

C-17 ya implementa en `backend/app/api/admin.py` consulta de auditoría, solicitud/estado/descarga de exportaciones y audit logging. La ruta frontend `/admin` tiene un guard de propietario pero carga `AdminPlaceholder`. El modelo actual contiene datos básicos de clínica (`Tenant.nombre`, `moneda`, `slug_reserva`) y usuarios/roles tenant-scoped.

## Goals / Non-Goals

**Goals:** un panel visible para propietario; mostrar y editar nombre/moneda del consultorio; listar usuarios y permitir crear cuentas con uno de los cuatro roles existentes; consultar auditoría y exportar; conservar los contratos/guards.

**Non-Goals:** alta de tenants, recuperación/invitación por correo, reset/desactivación o cambio de rol de usuarios existentes, edición de agenda/catálogo, pagos, gestión de sucursales, secretos de proveedores y features E2.

## Decisions

- Extender el router `/api/admin` existente y usar `tenant_session`; el tenant siempre se deriva del principal validado y se refuerza con RLS.
- Alta de usuario recibe contraseña inicial explícita (10–256 caracteres), la guarda con Argon2id y nunca la devuelve. Unicidad de email por tenant existente; error uniforme 409.
- El alta de cuenta asigna exactamente un rol del catálogo permitido, excluyendo `propietario` para evitar transferencias/acumulación accidental de autoridad desde el panel. El propietario inicial sigue creado por seed.
- Perfil modifica solo `nombre` y `moneda` (`ARS` en el MVP); slug, plan e identidad tenant no son editables.
- El frontend expone cuatro secciones accesibles y carga/errores/éxito vacíos, empleando `ApiClient`; la exportación sigue el contrato de trabajo asíncrono existente.
- No hace falta migración: se usan columnas y constraints actuales.

## Risks / Trade-offs

- Contraseña inicial ingresada manualmente exige comunicación segura entre propietario y usuario; no existe correo de invitación en el MVP. La UI aclara que debe compartirse fuera del sistema y el servidor almacena solo el hash.
- No se ofrecen operaciones peligrosas sobre cuentas existentes; pueden agregarse luego con estrategia de revocación de sesiones.
- Una descarga puede demorar mientras el worker prepara el ZIP; la UI presenta estado y permite consultar/descargar cuando esté listo.

## Validation

- Tests backend: permisos, tenant/RLS, validaciones, hash Argon2id, conflicto de email, edición permitida de perfil.
- Tests frontend: propietario carga secciones/acciones y errores; rol no propietario sigue en 403; sin regresión de rutas.
- Suite backend/frontend y build de producción.
