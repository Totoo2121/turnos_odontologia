# Spec Delta

## Purpose

Da al equipo clínico una ficha web única donde documentar la atención del paciente
(HCE, evoluciones, odontograma, adjuntos, presupuestos y consentimientos) y cerrar
el turno, respetando la visibilidad clínica por rol.

## ADDED Requirements

### Requirement: Ficha de paciente con bloque administrativo y clínico

La app SHALL mostrar `/pacientes/:id` con los datos administrativos del paciente a
todo el staff y las pestañas clínicas solo a propietario u odontólogo con acceso
clínico; recepción y asistente SHALL ver únicamente el bloque administrativo.

#### Scenario: Odontólogo tratante ve las pestañas clínicas

- **WHEN** un odontólogo tratante del paciente abre `/pacientes/:id`
- **THEN** ve el bloque administrativo y las pestañas de HCE, odontograma, adjuntos, presupuestos y consentimientos

#### Scenario: Recepción ve la ficha sin datos clínicos

- **WHEN** un usuario de recepción abre `/pacientes/:id`
- **THEN** ve los datos administrativos y ninguna pestaña que exponga evoluciones, piezas, adjuntos o presupuestos

#### Scenario: Profesional ajeno no ve datos clínicos

- **WHEN** un odontólogo sin turno ni derivación abre la ficha y el backend responde 403 en las lecturas clínicas
- **THEN** la app muestra un aviso de acceso clínico restringido sin renderizar datos de la historia

### Requirement: Anamnesis y evoluciones append-only

La app SHALL mostrar la anamnesis y las evoluciones de la historia clínica con autor
y fecha, y SHALL permitir agregar una evolución nueva sin ofrecer edición ni
borrado; una corrección SHALL registrarse como una evolución nueva que referencia
la anterior.

#### Scenario: Lectura de la historia

- **WHEN** un odontólogo con acceso clínico abre la pestaña de HCE
- **THEN** ve la anamnesis y las evoluciones ordenadas con su autor y fecha

#### Scenario: Alta de evolución

- **WHEN** el odontólogo completa el texto de una evolución y la envía
- **THEN** la evolución aparece al final de la lista con su autor tomado de la sesión

#### Scenario: Corrección sin edición destructiva

- **WHEN** el odontólogo corrige una evolución existente
- **THEN** la app crea una evolución nueva con `corrige_evolucion_id` y no expone acciones de editar o borrar

### Requirement: Odontograma FDI interactivo por pieza y superficie

La app SHALL renderizar el odontograma FDI con las 32 piezas permanentes, mostrar el
estado actual por pieza y superficie, y SHALL permitir registrar un evento nuevo
validando la combinación estado–superficie antes de enviarlo al backend.

#### Scenario: Render del odontograma completo

- **WHEN** el odontólogo abre la pestaña de odontograma
- **THEN** ve las 32 piezas agrupadas por arcada y el estado vigente de cada una

#### Scenario: Evento con superficie

- **WHEN** registra `caries` en la pieza `16` con superficie `oclusal`
- **THEN** el evento se agrega y la pieza refleja el estado actualizado

#### Scenario: Superficie prohibida

- **WHEN** intenta registrar `corona` con una superficie
- **THEN** la app bloquea el envío con un error de validación y no llama a la API

#### Scenario: Pieza fuera del rango FDI

- **WHEN** el identificador de pieza enviado no está entre 11 y 48
- **THEN** la app muestra el error 422 del backend sin actualizar el odontograma

### Requirement: Adjuntos clínicos de la historia

La app SHALL listar los adjuntos de la historia, permitir subir una imagen o PDF con
tipo y origen mediante `multipart/form-data`, y abrir cada adjunto con la URL
firmada devuelta por el backend; SHALL NOT enviar `turno_id` en la subida.

#### Scenario: Subida válida

- **WHEN** el odontólogo sube un PDF ficticio de tipo `rx` con origen `consulta`
- **THEN** el adjunto aparece en la lista con su nombre, tipo y tamaño

#### Scenario: Archivo rechazado

- **WHEN** el archivo supera el tamaño máximo o su MIME no está permitido
- **THEN** la app muestra el error 422 y no agrega el adjunto a la lista

#### Scenario: Apertura con URL firmada

- **WHEN** el odontólogo abre un adjunto listado
- **THEN** la app solicita la URL firmada vigente y abre el archivo sin exponer la clave de storage

### Requirement: Presupuestos armados desde la ficha clínica

La app SHALL listar los presupuestos del paciente y permitir armar uno con ítems de
prestación, cantidad, pieza/superficie opcional y etapa, mostrando el total en ARS
calculado por el servidor, y SHALL exponer enviar, aceptar y rechazar según el
estado y el resultado del gate de consentimiento.

#### Scenario: Armado con dos ítems

- **WHEN** el odontólogo agrega dos ítems ficticios y guarda el presupuesto
- **THEN** la app muestra el presupuesto en `borrador` con el total exacto devuelto por la API

#### Scenario: Aceptación con consentimiento

- **WHEN** el presupuesto enviado es invasivo, el paciente tiene consentimiento firmado y el odontólogo acepta
- **THEN** la ficha muestra el plan generado y la deuda reflejada en la cuenta corriente

#### Scenario: Aceptación bloqueada por consentimiento

- **WHEN** el presupuesto enviado es invasivo y no hay consentimiento firmado
- **THEN** la app muestra el bloqueo 409 `consentimiento_requerido` y el presupuesto sigue en `enviado`

#### Scenario: Recepción sin acciones de presupuesto

- **WHEN** recepción abre la ficha de un paciente con presupuestos
- **THEN** no ve botones para crear, enviar, aceptar ni rechazar presupuestos

### Requirement: Consentimientos firmados desde la ficha

La app SHALL listar los consentimientos del paciente, permitir firmar uno con tipo,
texto, versión, firmante y marca de plan invasivo, y SHALL mostrar el estado de
verificación del hash y permitir abrir el PDF generado.

#### Scenario: Firma registrada

- **WHEN** el odontólogo completa la firma ficticia y la envía
- **THEN** el consentimiento aparece en la lista con firmante, fecha y hash verificado

#### Scenario: PDF del consentimiento

- **WHEN** el odontólogo abre el PDF de un consentimiento listado
- **THEN** la app descarga el PDF asociado sin exponer la clave de storage

#### Scenario: Firma incompleta

- **WHEN** se envía la firma sin texto o sin firmante
- **THEN** la app muestra el error de validación y no crea el consentimiento

### Requirement: Cierre de turno y agendado del control

La app SHALL permitir marcar un turno del paciente como `atendido` a los roles con
escritura de agenda y SHALL mostrar la fecha de control sugerida por el intervalo
de la prestación; agendar el turno de control SHALL estar disponible solo para los
roles con permiso de creación de agenda.

#### Scenario: Cierre como atendido

- **WHEN** el odontólogo o recepción marca como `atendido` el turno abierto del paciente
- **THEN** el turno refleja el estado `atendido` en la ficha y en la agenda

#### Scenario: Fecha de control sugerida

- **WHEN** el odontólogo abre la ficha de un paciente con una prestación que tiene intervalo de control
- **THEN** ve la fecha sugerida para el próximo control sin poder crear el turno por sí mismo

#### Scenario: Recepción agenda el control

- **WHEN** recepción agenda el control desde la ficha con la prestación y fecha elegidas
- **THEN** el turno nuevo aparece en la agenda del profesional con la prestación y fecha elegidas

#### Scenario: Conflicto de agenda

- **WHEN** el horario elegido para el control se solapa con otro turno o un bloqueo
- **THEN** la app muestra el conflicto 409 y no crea el turno

### Requirement: Acciones ocultas y errores de dominio legibles

La app SHALL ocultar las acciones que el rol no puede ejecutar y SHALL traducir los
errores 403, 404, 409 y 422 del backend a mensajes legibles sin revelar datos de
otros tenants ni detalles internos.

#### Scenario: Acción no permitida oculta

- **WHEN** un asistente abre la ficha
- **THEN** no ve acciones de evolución, presupuesto, consentimiento ni cierre de turno

#### Scenario: Error de dominio visible

- **WHEN** una operación responde 409 porque el presupuesto ya no está en borrador
- **THEN** la app muestra el mensaje de dominio y recarga el estado vigente
