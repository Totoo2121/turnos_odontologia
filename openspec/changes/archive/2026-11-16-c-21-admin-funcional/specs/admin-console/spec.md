## ADDED Requirements

### Requirement: Administración de clínica y usuarios por propietario
La app MUST ofrecer al propietario un panel operativo que muestre el perfil de su consultorio y sus usuarios, permita actualizar el nombre/moneda y crear usuarios con roles del catálogo, y nunca permita acceder a datos de otro tenant.

#### Scenario: Actualizar el perfil
- **WHEN** el propietario guarda un nombre válido y la moneda habilitada
- **THEN** el sistema persiste los campos permitidos y devuelve el perfil actualizado
- **AND** no permite cambiar el slug, el tenant ni el plan

#### Scenario: Crear usuario del equipo
- **WHEN** el propietario envía email, nombre, contraseña inicial y rol permitido
- **THEN** la cuenta pertenece al tenant del propietario y la contraseña queda almacenada mediante Argon2id
- **AND** la respuesta no contiene contraseña ni hash

#### Scenario: Rechazo de administración
- **WHEN** un usuario sin rol propietario invoca una operación administrativa
- **THEN** la API responde 403 y no realiza cambios

### Requirement: Auditoría y exportación accesibles desde Admin
El panel Admin MUST exponer la auditoría tenant-scoped y el ciclo de exportación existente, informando estados y habilitando la descarga autenticada cuando el archivo esté disponible.

#### Scenario: Solicitar y consultar exportación
- **WHEN** el propietario solicita exportar sus datos
- **THEN** la UI crea un trabajo, muestra su estado y ofrece descargarlo al quedar listo
- **AND** la descarga conserva auditoría y expiración del contrato existente
