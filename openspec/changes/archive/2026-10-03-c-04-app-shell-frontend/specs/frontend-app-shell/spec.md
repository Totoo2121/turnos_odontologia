# Spec Delta — frontend-app-shell

## Purpose

El shell web autenticado del SaaS: routing, sesión contra la API C-03, guards por rol según la matriz RBAC, layout con navegación por rol, librería UI mínima y páginas placeholder que reservan el contrato de las features futuras.

## ADDED Requirements

### Requirement: Sesión web contra la API C-03 sin rediseñar el refresh

El sistema SHALL autenticar la app web contra `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/refresh` y `POST /api/auth/logout`, reutilizando el api-client cookie-based de C-03 (refresh solo en cookie HttpOnly, reintento único ante 401) y el `auth-store` Zustand extendido como única fuente de sesión.

#### Scenario: Login válido establece sesión y redirige a la ruta por defecto del rol

- **WHEN** un usuario con credenciales válidas envía email + password en `/login`
- **THEN** la app guarda solo el access token en memoria/store versionado (nunca el refresh en JS), carga `GET /api/auth/me` y redirige a su ruta por defecto (p. ej. recepción → `/agenda`)

#### Scenario: Credencial inválida muestra error genérico sin revelar causa

- **WHEN** el login responde 401
- **THEN** la app muestra un error genérico (sin distinguir email/password), no guarda sesión y permanece en `/login`

#### Scenario: Access expirado se renueva una vez y la sesión continúa

- **WHEN** una request autenticada recibe 401 con refresh en cookie vigente
- **THEN** el api-client pide `POST /api/auth/refresh` una sola vez, reintenta la request original y la sesión continúa sin intervención del usuario

#### Scenario: Refresh rechazado cierra la sesión local

- **WHEN** el refresh responde 401 (rotado, revocado o expirado)
- **THEN** la app limpia el access almacenado, resetea el store y redirige a `/login` sin reintentar

#### Scenario: Logout invalida y limpia

- **WHEN** el usuario acciona cerrar sesión
- **THEN** la app llama `POST /api/auth/logout`, limpia el access almacenado y el store, y redirige a `/login` aunque el logout remoto falle

### Requirement: Guards de ruta por rol según la matriz RBAC

El sistema SHALL proteger cada ruta privada con `RequireAuth` (sesión válida) y `RequireRole` (al menos uno de los roles permitidos de la ruta), redirigiendo a `/login` sin sesión y a `/403` sin permiso, usando exactamente los roles de la matriz KB 03 (`propietario|odontologo|recepcion|asistente`).

#### Scenario: Anónimo en ruta privada va a login con retorno

- **WHEN** un visitante sin sesión abre `/agenda`
- **THEN** es redirigido a `/login` recordando la ruta original para volver tras autenticarse

#### Scenario: Rol sin permiso ve 403

- **WHEN** un usuario con rol `asistente` abre `/admin`
- **THEN** ve la página `403` (sin contenido del admin) y el nav no ofrece `/admin`

#### Scenario: Matriz rol×ruta del shell

- **WHEN** se evalúa el acceso por rol
- **THEN** rige: `/agenda` → propietario, odontologo, recepcion, asistente; `/pacientes` → propietario, odontologo, recepcion, asistente; `/caja` → propietario, recepcion, odontologo (solo lectura, el cobro lo cierra C-15); `/reportes` → propietario, recepcion, odontologo (cada uno ve su alcance en C-16); `/admin` → solo propietario

#### Scenario: Guard reacciona al cambio de roles en caliente

- **WHEN** la sesión cambia (login/logout/refresh con roles distintos) con una ruta privada abierta
- **THEN** el guard reevalúa sin recarga manual y redirige a `/403` o `/login` según corresponda

### Requirement: Layout shell con navegación por rol

El sistema SHALL renderizar las rutas privadas dentro de `AppShell` (header con usuario + logout, nav con solo las rutas permitidas al rol, outlet de contenido) y `/login` en un layout de autenticación sin navegación privada; rutas desconocidas muestran `NotFound` dentro del layout que corresponda a la sesión.

#### Scenario: Shell por rol filtra navegación

- **WHEN** un usuario `recepcion` autenticado abre cualquier ruta privada
- **THEN** el nav muestra agenda, pacientes, caja y reportes, y oculta admin

#### Scenario: Header permite cerrar sesión desde cualquier página privada

- **WHEN** el usuario acciona logout en el header
- **THEN** se ejecuta el flujo de logout y termina en `/login`

#### Scenario: Ruta desconocida con sesión muestra NotFound sin romper el shell

- **WHEN** un usuario autenticado abre `/ruta-que-no-existe`
- **THEN** ve la página NotFound dentro del `AppShell` (header/nav intactos)

### Requirement: Páginas placeholder con contrato congelado para features futuras

El sistema SHALL reservar `/agenda`, `/pacientes`, `/pacientes/:id`, `/caja`, `/reportes` y `/admin` con páginas placeholder que declaran titular, estado vacío y (donde aplique) el parámetro de ruta, sin lógica de dominio; los changes C-07/C-15/C-16 reemplazan el contenido respetando path, params y guards.

#### Scenario: Cada ruta futura renderiza su placeholder identificable

- **WHEN** un rol permitido abre cada ruta privada antes de su change de contenido
- **THEN** ve un placeholder con el nombre del módulo y mensaje de "contenido en su change" (sin tablas ni formularios de dominio)

#### Scenario: Detalle de paciente expone el parámetro de ruta

- **WHEN** un rol permitido abre `/pacientes/abc-123`
- **THEN** el placeholder muestra el identificador `abc-123` tal cual viene en la URL (contrato `:id` que C-12/C-15 reutilizan)

### Requirement: Librería shared/ui mínima y componible

El sistema SHALL proveer en `shared/ui` los componentes `Table`, `Modal`, `Form` (Field + error + validación mínima) y `Toast` con props controladas, sin dependencias CSS nuevas, usables desde cualquier placeholder y feature futura.

#### Scenario: Componentes renderizan y se controlan por props

- **WHEN** una página renderiza `Table` con columnas+filas ficticias, `Modal` abierto/cerrado por prop, `Form/Field` con error visible y `Toast` con mensaje
- **THEN** cada componente refleja exactamente sus props (abierto muestra, cerrado no; error muestra el texto) sin estado global oculto

#### Scenario: Sin framework CSS nuevo

- **WHEN** se inspeccionan las dependencias del frontend tras el change
- **THEN** la única dependencia de runtime agregada respecto de C-03 es el router; no hay Tailwind/MUI/Chakra

### Requirement: Web responsive sin nativas, sin PWA y sin secretos en cliente

El sistema SHALL ser usable en viewport móvil y desktop con CSS responsive (sin lógica de breakpoints en JS salvo necesidad demostrada), SHALL NOT incluir apps nativas ni service-worker PWA, SHALL NOT persistir el refresh token ni secretos en JS/storage, y SHALL usar solo datos ficticios marcados en placeholders y tests.

#### Scenario: Layout colapsa en móvil

- **WHEN** se abre cualquier ruta privada en viewport ≤ 480px
- **THEN** la navegación colapsa (menú/hamburguesa o equivalente) y el contenido no requiere scroll horizontal para la acción principal

#### Scenario: Sin refresh ni secretos en almacenamiento JS

- **WHEN** se inspecciona el almacenamiento versionado y el código tras login
- **THEN** solo hay access token (clave `turnos.auth.v1`); no hay refresh token, ni `MP_ACCESS_TOKEN`, ni `WA_BSP_TOKEN`, ni `JWT_SECRET` en ningún bundle, ejemplo o test
