# Spec Delta

## Purpose

Permite a pacientes en espera recibir ofertas de huecos liberados por orden de antigüedad y preferencia, reduciendo huecos vacíos y adelantando atención, con vencimiento y rotación automática.

## ADDED Requirements

### Requirement: Alta en lista de espera
El sistema MUST permitir a un paciente inscribirse en la lista de espera por prestación y franja preferida, con profesional opcional, en estado `activa`.

#### Scenario: Inscripción válida
- **WHEN** se recibe `POST /lista-espera` con paciente, prestación y franja válidos
- **THEN** se crea registro en estado `activa` con `created_at` y se devuelve 201.

### Requirement: Oferta por orden de antigüedad y preferencia
Al liberarse un hueco compatible, el sistema MUST ofrecerlo al registro `activa` más antiguo compatible por prestación/franja/profesional, marcándolo `ofrecida` con vencimiento.

#### Scenario: Hueco liberado ofrece al más antiguo compatible
- **WHEN** se libera un hueco compatible con prestación P y franja F
- **THEN** el registro activo más antiguo compatible pasa a `ofrecida` con fecha de vencimiento y los demás permanecen `activa`.

### Requirement: Vencimiento rota al siguiente
Si una oferta vence sin aceptación, el sistema MUST marcarla `vencida` y ofrecer el hueco al siguiente registro compatible.

#### Scenario: Oferta vencida rota
- **WHEN** vence el plazo de una oferta sin aceptación
- **THEN** el registro pasa a `vencida` y el siguiente compatible más antiguo pasa a `ofrecida`.

### Requirement: Conversión a turno normal
La aceptación de una oferta MUST crear un turno normal que respete RN-AG-01, RN-AG-02 y RN-AG-05, marcando el registro `convertida`.

#### Scenario: Aceptación crea turno
- **WHEN** el paciente acepta la oferta dentro del vencimiento
- **THEN** se crea turno normal validando anti-solapamiento y bloqueos; el registro pasa a `convertida`.

### Requirement: Aislamiento multi-tenant
La tabla `lista_espera` MUST tener RLS + FORCE RLS por `tenant_id`.

#### Scenario: Aislamiento por tenant
- **WHEN** un tenant consulta lista de espera
- **THEN** solo ve registros de su tenant.