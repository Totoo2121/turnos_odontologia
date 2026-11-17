# Frontend Visual System Specification

## Purpose

Definir una experiencia visual coherente, minimalista, accesible y adecuada a una aplicación odontológica en todas las superficies del frontend.

## ADDED Requirements

### Requirement: Lenguaje visual compartido

El frontend MUST usar tokens compartidos para color, tipografía, espaciado, bordes, foco y superficies en el shell, agenda, pacientes, pestañas clínicas, caja, reportes, acceso y rutas públicas.

#### Scenario: Consistencia entre secciones

- **WHEN** un usuario navega entre agenda, pacientes/ficha, caja y reportes
- **THEN** reconoce el mismo sistema de navegación, controles, superficies, jerarquía y estados activos
- **AND** las acciones primarias usan el color de marca y los estados de error/aviso conservan significado consistente

### Requirement: Paleta clínica minimalista

La interfaz MUST priorizar fondos claros cálidos, texto de alto contraste y una paleta contenida de verde petróleo/turquesa y menta. MUST reservar los tonos de error y advertencia para estados semánticos y no comunicar estado solo mediante color.

#### Scenario: Estado semántico reconocible

- **WHEN** se muestra un estado de turno, pago, consentimiento, carga o error
- **THEN** el estado incluye texto legible y, cuando corresponda, icono además del color
- **AND** el color mantiene el significado en todas las pestañas

### Requirement: Accesibilidad y adaptación de pantalla

El frontend MUST conservar flujos y datos mientras ofrece contraste WCAG AA, foco de teclado visible, controles etiquetados y layout responsive.

#### Scenario: Navegación por teclado

- **WHEN** el usuario recorre navegación, pestañas, botones y formularios con teclado
- **THEN** el foco es visible, el orden de interacción es lógico y la selección actual se identifica sin depender del color

#### Scenario: Pantalla angosta y zoom

- **WHEN** el usuario utiliza una pantalla de 360 px o zoom de 200%
- **THEN** navegación y controles principales siguen siendo accesibles sin scroll horizontal global
- **AND** una tabla ancha puede desplazarse dentro de su propio contenedor

### Requirement: Presentación sin regresión funcional

El refinamiento visual MUST conservar rutas, permisos por rol, operaciones, textos de validación, estados vacíos/error/carga y contratos API existentes.

#### Scenario: Flujo existente preservado

- **WHEN** un usuario realiza las acciones ya disponibles en agenda, ficha clínica, caja o reportes
- **THEN** se ejecutan los mismos contratos y reglas de negocio con los mismos permisos y resultados
- **AND** solo cambia la presentación visual
