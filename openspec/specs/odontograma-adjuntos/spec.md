# odontograma-adjuntos Specification

## Purpose
Extiende la historia clínica con el odontograma FDI por eventos inmutables, los adjuntos RX/fotos almacenados de forma privada y los consentimientos firmados verificables que habilitan los planes invasivos.

## Requirements

### Requirement: Odontograma único por historia clínica

El sistema SHALL mantener como máximo un odontograma por historia clínica dentro del tenant y SHALL devolver el existente en lugar de crear otro.

#### Scenario: Primera lectura

- **WHEN** un usuario con acceso clínico consulta el odontograma de una historia que no tiene uno
- **THEN** el sistema crea y devuelve un odontograma vacío para esa historia

#### Scenario: Segunda lectura

- **WHEN** se vuelve a consultar el odontograma de la misma historia
- **THEN** el sistema devuelve el mismo odontograma y no crea una fila nueva

### Requirement: Eventos de pieza con nomenclatura FDI

El sistema SHALL registrar cada evento con pieza FDI válida, superficie válida cuando corresponda, estado, fecha y autor (RN-HC-02).

#### Scenario: Evento válido

- **WHEN** un odontólogo tratante registra la pieza `16`, superficie `oclusal`, estado `caries`
- **THEN** el sistema persiste el evento con fecha y autor tomados del pedido y del token

#### Scenario: Pieza FDI inválida

- **WHEN** se envía una pieza fuera del rango FDI 11–48 o con dentición/unidad inválida
- **THEN** el sistema rechaza la operación con 422 y no registra el evento

#### Scenario: Superficie inválida

- **WHEN** se envía una superficie que no pertenece al catálogo permitido
- **THEN** el sistema rechaza la operación con 422 y no registra el evento

### Requirement: Estado actual derivado del último evento

El sistema SHALL exponer el estado actual por pieza y superficie como el evento más reciente, sin sobrescribir eventos anteriores.

#### Scenario: Cambio de estado

- **WHEN** existe un evento `caries` y luego se registra `obturacion` para la misma pieza y superficie
- **THEN** la lectura del odontograma muestra `obturacion` como estado actual y conserva ambos eventos en el historial

#### Scenario: Estados de pieza completa

- **WHEN** se registra un estado que aplica a toda la pieza, como `extraccion` o `corona`, sin superficie
- **THEN** el sistema lo acepta y lo refleja como estado de la pieza completa

### Requirement: Eventos de odontograma append-only

El sistema SHALL impedir la edición y el borrado de eventos de odontograma, tanto por API como por base de datos.

#### Scenario: Corrección de un evento

- **WHEN** el odontólogo necesita corregir un estado
- **THEN** registra un nuevo evento y el anterior permanece inmutable en el historial

#### Scenario: Intento de escritura destructiva

- **WHEN** se intenta actualizar o borrar un evento por API o por SQL directo
- **THEN** la operación falla y el evento original queda intacto

### Requirement: Visibilidad clínica del odontograma

El sistema SHALL permitir leer y escribir el odontograma solo al propietario, al profesional tratante o a un profesional con derivación explícita, y SHALL rechazar a recepción y asistente.

#### Scenario: Profesional tratante

- **WHEN** un odontólogo con al menos un turno del paciente abre el odontograma
- **THEN** puede leer el estado actual y registrar eventos

#### Scenario: Profesional ajeno

- **WHEN** un odontólogo sin turnos ni derivación intenta leer el odontograma
- **THEN** el sistema responde 403 sin revelar datos clínicos

#### Scenario: Recepción

- **WHEN** recepción o asistente intenta acceder al odontograma
- **THEN** el sistema responde 403

### Requirement: Adjuntos ligados a la historia clínica

El sistema SHALL asociar cada adjunto a una historia clínica y SHALL rechazar cualquier asociación a un turno (RN-HC-05).

#### Scenario: Subida de RX

- **WHEN** un profesional con acceso clínico sube una RX a la historia
- **THEN** el adjunto queda ligado a `historia_clinica_id` y es visible al consultar esa historia

#### Scenario: Intento de adjuntar a un turno

- **WHEN** se envía un `turno_id` en lugar de una historia clínica
- **THEN** el sistema rechaza la operación con 422 y no persiste el adjunto

### Requirement: Metadatos verificables del adjunto

El sistema SHALL registrar tipo, nombre original, MIME, tamaño y SHA-256 de cada adjunto, y SHALL rechazar tipos o tamaños fuera de los límites configurados.

#### Scenario: Adjunto aceptado

- **WHEN** se sube un archivo JPEG dentro del tamaño máximo
- **THEN** el sistema guarda el archivo en storage privado y persiste su hash y metadatos

#### Scenario: Adjunto rechazado

- **WHEN** se sube un archivo con MIME no permitido o que supera el tamaño máximo
- **THEN** el sistema rechaza la operación con 422 y no escribe el archivo

### Requirement: URLs firmadas expirables para adjuntos

El sistema SHALL entregar el contenido de un adjunto solo mediante una URL firmada con expiración y alcance de tenant.

#### Scenario: URL válida

- **WHEN** un usuario con acceso clínico solicita la URL de un adjunto
- **THEN** recibe una URL firmada con vencimiento y puede descargar el contenido mientras siga vigente

#### Scenario: URL expirada o adulterada

- **WHEN** se usa una URL vencida o con la firma alterada
- **THEN** el sistema responde 403 y no entrega el archivo

#### Scenario: URL de otro tenant

- **WHEN** un usuario usa una URL firmada emitida para otra historia o tenant
- **THEN** el sistema no expone el contenido a ese usuario

### Requirement: Consentimiento firmado con hash verificable

El sistema SHALL registrar cada consentimiento con un hash SHA-256 de un payload canónico, timestamp de firma, IP y dispositivo, y SHALL poder verificar el hash al leerlo (RN-HC-04).

#### Scenario: Firma registrada

- **WHEN** se crea un consentimiento con firmante, tipo y texto
- **THEN** el sistema guarda el hash, el timestamp, la IP y el dispositivo, y devuelve el consentimiento

#### Scenario: Verificación correcta

- **WHEN** se lee un consentimiento cuyo contenido no cambió
- **THEN** el sistema devuelve `hash_valido: true`

#### Scenario: Contenido alterado

- **WHEN** el payload almacenado no coincide con el hash registrado
- **THEN** el sistema devuelve `hash_valido: false` sin modificar el registro

### Requirement: PDF del consentimiento generado y recuperable

El sistema SHALL generar un PDF del consentimiento que incluya sus datos y el hash de firma, y SHALL permitir recuperarlo mediante una URL firmada expirable.

#### Scenario: Generación

- **WHEN** se crea un consentimiento
- **THEN** el sistema genera el PDF, lo guarda en storage privado y persiste su `storage_key` y su propio SHA-256

#### Scenario: Descarga

- **WHEN** un usuario con acceso clínico solicita el PDF
- **THEN** el sistema responde con una URL firmada y expirable hacia el PDF

#### Scenario: PDF de otro tenant

- **WHEN** un usuario sin acceso clínico intenta obtener el PDF de otro tenant
- **THEN** el sistema responde 404 sin revelar su existencia

### Requirement: Consentimiento exigible para planes invasivos

El sistema SHALL exponer una verificación de consentimiento invasivo vigente por paciente para que C-14 bloquee planes invasivos sin firma (RN-HC-04).

#### Scenario: Paciente con consentimiento invasivo

- **WHEN** existe al menos un consentimiento marcado como invasivo para el paciente
- **THEN** la verificación devuelve que el consentimiento está presente

#### Scenario: Paciente sin consentimiento invasivo

- **WHEN** no existe consentimiento invasivo para el paciente
- **THEN** la verificación devuelve que el consentimiento falta y el listado del paciente no lo incluye

### Requirement: Aislamiento multi-tenant de odontograma, adjuntos y consentimientos

El sistema SHALL aplicar RLS + FORCE RLS en las cuatro tablas nuevas y SHALL responder 404 ante recursos de otro tenant.

#### Scenario: Lectura cruzada

- **WHEN** un usuario del tenant A solicita un odontograma, adjunto o consentimiento del tenant B
- **THEN** el sistema responde 404 sin revelar su existencia

#### Scenario: RLS sin GUC

- **WHEN** una sesión de base de datos consulta las tablas nuevas sin `app.tenant_id` fijado
- **THEN** la política falla cerrada y no devuelve filas de ningún tenant

### Requirement: Autoría tomada del token

El sistema SHALL tomar el autor de eventos y consentimientos desde el `sub` del token y SHALL ignorar cualquier autor enviado en el cuerpo.

#### Scenario: Autor explícito en el body

- **WHEN** el cuerpo incluye un `autor_usuario_id` distinto al del token
- **THEN** el sistema ignora ese valor y persiste el usuario autenticado

#### Scenario: Token sin identificador válido

- **WHEN** el `sub` del token no es un UUID
- **THEN** el sistema rechaza la escritura con 422
