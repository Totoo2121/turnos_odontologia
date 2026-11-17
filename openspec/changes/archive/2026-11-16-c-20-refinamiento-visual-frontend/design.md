# Diseño — C-20

## Enfoque

Crear una capa común de diseño CSS sin introducir librerías. Definir variables globales y estilos base en `frontend/src/styles/` y reutilizar componentes existentes de `shared/ui`. Reemplazar estilos aislados solo donde haga falta para que las áreas completas compartan tokens y estados.

## Sistema visual

| Token | Valor inicial | Uso |
|---|---|---|
| `--color-ink` | `#173D35` | títulos, navegación y texto principal |
| `--color-primary` | `#167C72` | acciones y enlaces principales |
| `--color-primary-hover` | `#11665E` | interacción hover |
| `--color-selection` | `#E5F3EF` | pestaña, fila o control seleccionado |
| `--color-canvas` | `#F6F8F6` | fondo general |
| `--color-surface` | `#FFFFFF` | paneles y formularios |
| `--color-border` | `#D8E3DE` | contornos y divisores |
| `--color-muted` | `#52645E` | texto secundario |
| `--color-danger` | `#A33D36` | error y acción destructiva |
| `--color-warning` | `#8A5A12` | atención requerida |

Los tokens son punto de partida; validar contraste y ajustar valores durante la implementación. No sacrificar AA por conservar un matiz. Estados exitosos y pendientes tendrán etiqueta textual/iconográfica además del tono.

## Superficies

- Shell: navegación clara, estado activo evidente, encabezados consistentes y contenido centrado con ancho útil para tablas.
- Agenda, caja y reportes: priorizar densidad legible y datos alineados; mantener desplazamiento horizontal contenido en tablas cuando sea necesario.
- Pacientes y ficha: pestañas distinguibles, paneles clínicos sobrios, formularios con foco fuerte y jerarquía estable entre datos administrativos y clínicos.
- Login, turno público y portal: conservar sus flujos y contenido con la misma tipografía, controles y paleta.
- Placeholders: seguir el shell, sin simular funcionalidad.

## Accesibilidad y responsive

Usar estados `:focus-visible`, etiquetas conectadas a controles, objetivos táctiles apropiados y contraste mínimo WCAG AA (4.5:1 para texto normal, 3:1 para texto grande y componentes). A 360 px las pantallas no deben provocar scroll horizontal global; permitir scroll interno solo para tablas/datos tabulares. Respetar `prefers-reduced-motion` y mantener la interfaz usable a zoom 200%.

## Riesgos y mitigaciones

- **CSS legado con selectores globales:** introducir tokens y estilos por componente; evitar overrides globales frágiles.
- **Densidad de vistas clínicas:** mejorar jerarquía sin ocultar datos ni alargar tareas repetidas.
- **Cambios accidentales en comportamiento:** limitar el change a presentación y verificar rutas, permisos, contratos y estados existentes.
