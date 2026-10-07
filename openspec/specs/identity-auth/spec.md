# identity-auth Specification

## Purpose

Esta capacidad responde, para cada request, quién llama, de qué tenant y qué puede hacer: autentica usuarios por credencial, emite y rota sesiones JWT, y autoriza cada acceso por matriz rol×recurso con aislamiento total por tenant.

## Requirements

### Requirement: Login por credencial emite sesión JWT

El sistema SHALL autenticar `POST /api/auth/login` con email + password dentro de un tenant y, si la credencial es válida, responder el par access (corto) + refresh (rotado) con claims `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat`, `exp`.

#### Scenario: Login válido emite par de tokens

- **WHEN** un usuario activo envía email + password correctos de su tenant a `POST /api/auth/login`
- **THEN** responde 200 con access token (`type=access`) y refresh token (`type=refresh`), ambos con `tenant_id` del usuario y sus roles vigentes

#### Scenario: Credencial inválida no distingue causa

- **WHEN** se envía email inexistente o password incorrecto (incluido email con mayúsculas equivalentes al registrado)
- **THEN** responde 401 con error genérico, sin revelar si el email existe, y no emite ningún token

#### Scenario: Login limitado a 5 intentos por 60 segundos

- **WHEN** una misma combinación IP+email supera 5 intentos en 60 segundos
- **THEN** el sexto intento responde 429 aunque la credencial sea correcta, y el contador se libera pasada la ventana

### Requirement: Access corto y refresh distinguible con expiración exigible

El sistema SHALL rechazar todo token expirado o con `type` incorrecto para el endpoint, y SHALL exigir `type=access` en recursos protegidos y `type=refresh` solo en `POST /api/auth/refresh`.

#### Scenario: Access expirado es rechazado

- **WHEN** un cliente llama un endpoint protegido con un access expirado
- **THEN** responde 401 y el api-client puede intentar el refresh una sola vez antes de fallar

#### Scenario: Refresh usado como access es rechazado

- **WHEN** un cliente presenta un refresh token como Bearer en un recurso protegido o en `GET /api/auth/me`
- **THEN** responde 401 sin ejecutar la operación

### Requirement: Refresh rota con detección de reuso

El sistema SHALL rotar el refresh en cada uso (emite un par nuevo e invalida el anterior) y SHALL tratar la reutilización de un refresh ya rotado como indicio de robo revocando la familia de sesión.

#### Scenario: Refresh válido rota el par

- **WHEN** un cliente envía un refresh vigente a `POST /api/auth/refresh`
- **THEN** responde 200 con un par nuevo (nuevo `jti`) y el refresh anterior queda inválido

#### Scenario: Reuso de refresh rotado revoca la sesión

- **WHEN** un cliente reintenta un refresh que ya fue rotado
- **THEN** responde 401 y los tokens derivados de esa familia dejan de ser aceptados

### Requirement: Logout revoca el access vigente

El sistema SHALL invalidar en `POST /api/auth/logout` el access presentado, de modo que su `jti` sea rechazado hasta su expiración natural.

#### Scenario: Token usado tras logout es rechazado

- **WHEN** un cliente llama `POST /api/auth/logout` con su access y luego reintenta un recurso protegido con ese mismo access
- **THEN** el logout responde 200 y el reintento posterior responde 401

### Requirement: Identidad del portador consultable

El sistema SHALL exponer `GET /api/auth/me` que devuelve `sub`, `tenant_id`, `roles` y `email` del access vigente.

#### Scenario: Me refleja roles vigentes

- **WHEN** un cliente autenticado con roles `recepcion` llama `GET /api/auth/me`
- **THEN** responde 200 con su `sub`, `tenant_id`, lista de roles que incluye `recepcion` y su `email`

#### Scenario: Me sin token es rechazado

- **WHEN** un cliente anónimo llama `GET /api/auth/me`
- **THEN** responde 401

### Requirement: Autorización por matriz rol×recurso (PermissionContext)

El sistema SHALL autorizar cada recurso protegido según la matriz de KB 03: propietario CRUD agenda/pacientes/cobros/config, R odontograma, R total reportes, R+ejecutar auditoría; odontólogo RUD sus turnos, CRUD sus pacientes, CRUD odontograma, R sus presupuestos, R propio reportes; recepción CRUD turnos, CR pacientes, R odontograma, CRUD cobros, R operativo; asistente R turnos, CR pacientes, R odontograma; paciente-portal CR/R propios y pagar propios.

#### Scenario: Recepción no accede a evoluciones clínicas (RN-SE-03)

- **WHEN** un usuario con rol `recepcion` intenta leer o escribir evoluciones clínicas
- **THEN** el sistema deniega con 403 (lectura de ficha básica de paciente sigue permitida según matriz)

#### Scenario: Odontólogo no ve HCE ajena sin derivación (RN-SE-02)

- **WHEN** un odontólogo pide la HCE de un paciente que no trata y sin derivación explícita registrada (ni rol propietario)
- **THEN** el sistema lo trata como inexistente o deniega con 403/404 sin revelar su contenido

#### Scenario: Propietario accede a reportes totales y auditoría

- **WHEN** un usuario con rol `propietario` pide reportes del tenant y la consulta de auditoría
- **THEN** recibe el total del tenant y puede ejecutar la exportación (otros roles reciben 403 en auditoría/exportación)

#### Scenario: Rol sin permiso recibe 403, no 404 ni 200 parcial

- **WHEN** un asistente intenta crear un cobro o ver reportes
- **THEN** responde 403 con error consistente y no ejecuta ningún efecto lateral

### Requirement: Tenant del token vincula todo acceso (RN-SE-01)

El sistema SHALL derivar el `tenant_id` de cada operación del access token validado (nunca de parámetros del cliente) y SHALL tratar todo registro de otro tenant como inexistente.

#### Scenario: Acceso cruzado por id es denegado

- **WHEN** un token del tenant A pide por id un recurso del tenant B
- **THEN** responde 404 (o 403) sin revelar el contenido del registro ajeno

#### Scenario: Token manipulado en tenant_id es rechazado

- **WHEN** un cliente presenta un access cuya firma no verifica (claims adulterados, incluido `tenant_id`)
- **THEN** responde 401 sin ejecutar la operación

### Requirement: Portal paciente por token firmado de un turno

El sistema SHALL emitir tokens de portal (`type=portal`) firmados, expirables y atados a un único turno, que autorizan `GET /p/{token}` sin sesión de usuario.

#### Scenario: Portal válido muestra solo su turno

- **WHEN** un paciente abre `GET /p/{token}` con un token de portal vigente
- **THEN** ve únicamente los datos de ese turno y ningún otro dato del tenant

#### Scenario: Portal expirado o ajeno es rechazado

- **WHEN** se usa un token de portal expirado, revocado o de otro turno/tenant
- **THEN** responde 401/404 sin exponer datos

### Requirement: Rutas públicas declaradas sin sesión

El sistema SHALL exponer sin JWT `GET /api/health`, el turnero `GET /reservar/{slug}`, el portal `GET /p/{token}` y los webhooks de Mercado Pago y WhatsApp (estos últimos autenticados por firma del proveedor), todos con rate-limit; turnero además con captcha.

#### Scenario: Health anónimo responde ok

- **WHEN** un cliente anónimo hace `GET /api/health` sin token
- **THEN** responde 200 y nunca 401/403

#### Scenario: Turnero exige captcha y limita intentos

- **WHEN** un cliente anónimo abusa del turnero o falla el captcha
- **THEN** la request es rechazada con 429 o 400 sin crear ningún turno (implementación del flujo de reserva en C-08; aquí solo la guarda)
