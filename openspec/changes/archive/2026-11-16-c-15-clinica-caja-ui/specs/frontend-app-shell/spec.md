# Spec Delta

## MODIFIED Requirements

### Requirement: Páginas placeholder con contrato congelado para features futuras

El sistema SHALL renderizar `/pacientes` como listado y búsqueda real de pacientes,
`/pacientes/:id` como ficha administrativa con pestañas clínicas según rol y
`/caja` como caja de mostrador real; solo `/reportes` y `/admin` SHALL permanecer
como placeholders hasta C-16/C-17, respetando path, params y guards existentes.

#### Scenario: Cada ruta futura renderiza su placeholder identificable

- **WHEN** un rol permitido abre `/reportes` o `/admin` antes de su change de contenido
- **THEN** ve un placeholder con el nombre del módulo y mensaje de "contenido en su change" (sin tablas ni formularios de dominio)

#### Scenario: Recepción busca un paciente desde el listado

- **WHEN** recepción abre `/pacientes` y escribe un apellido ficticio
- **THEN** ve los pacientes coincidentes del tenant y puede abrir su ficha

#### Scenario: Detalle de paciente expone el parámetro de ruta

- **WHEN** un rol permitido abre `/pacientes/abc-123`
- **THEN** la ficha usa el identificador `abc-123` de la URL para consultar al paciente

#### Scenario: Caja real en su ruta

- **WHEN** recepción abre `/caja`
- **THEN** ve la caja de mostrador con búsqueda de paciente y cierre del día, no el placeholder

#### Scenario: Placeholders restantes identificables

- **WHEN** un rol permitido abre `/reportes` o `/admin` antes de C-16/C-17
- **THEN** ve el placeholder del módulo con su mensaje de "contenido en su change"

#### Scenario: Guards no cambian

- **WHEN** un asistente abre `/caja`
- **THEN** es redirigido a `/403` como antes del change

## ADDED Requirements

### Requirement: ApiClient con verbos, multipart y errores de dominio

El sistema SHALL exponer en el api-client los verbos `GET`, `POST`, `PATCH`,
`DELETE` y una subida `multipart/form-data`, SHALL enviar el access token en todas
las llamadas autenticadas, SHALL reintentar una sola vez tras un 401 con refresh
vigente y SHALL exponer el `detail` del backend en el error de la feature.

#### Scenario: PATCH autenticado con refresh

- **WHEN** una feature envía un `PATCH` y el access expiró pero el refresh sigue vigente
- **THEN** el api-client renueva una vez, reintenta el `PATCH` y devuelve la respuesta

#### Scenario: Subida multipart

- **WHEN** la ficha sube un adjunto con `multipart/form-data`
- **THEN** el api-client envía el archivo con el token y sin fijar manualmente el `content-type` del boundary

#### Scenario: Error de dominio legible

- **WHEN** el backend responde 409 con `detail` de negocio
- **THEN** la feature recibe un `ApiError` con ese mensaje y puede mostrarlo al usuario

#### Scenario: Refresh rechazado limpia la sesión

- **WHEN** el refresh responde 401 durante un `PATCH` o una subida
- **THEN** el api-client limpia el access almacenado y la app vuelve a `/login` sin reintentar
