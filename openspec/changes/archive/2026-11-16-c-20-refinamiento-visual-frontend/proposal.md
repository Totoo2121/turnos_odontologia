# C-20 — Refinamiento visual del frontend

## Problema

Las pantallas del personal y las fichas clínicas se construyeron en changes distintos. Hoy mezclan estilos, colores, espaciados y componentes básicos; la aplicación se siente poco cohesionada y visualmente genérica para un producto odontológico.

## Resultado

Unificar las superficies del frontend con un sistema visual minimalista, cálido y clínico. Usar una paleta de verde azulado profundo, turquesa sereno, menta pálida y fondos marfil claros; mantener lectura rápida, jerarquía clara y controles consistentes.

## Alcance

- Establecer tokens de color, tipografía, espaciado, bordes, foco y elevación de baja intensidad.
- Aplicar el lenguaje visual al shell y navegación; login; agenda; pacientes y todas las pestañas de ficha (HCE, odontograma, adjuntos, consentimientos y presupuestos); caja; reportes; páginas públicas de reserva/portal y placeholders visibles.
- Unificar tablas, formularios, botones, pestañas, tarjetas, etiquetas de estado, avisos y diálogos.
- Verificar accesibilidad de contraste, foco/teclado, estados que no dependan solo del color y diseño responsive.

## Fuera de alcance

- Cambiar reglas de negocio, permisos, rutas, contratos API, contenido, datos o flujos.
- Añadir dependencias de UI o reemplazar React/Vite.
- Incorporar gráficos, ilustraciones o animaciones decorativas que dificulten la lectura clínica.

## Dependencias

C-04, C-07, C-15, C-16 y C-17, todos archivados. C-19 no es requisito: el refinamiento no cambia la persistencia ni las reglas de agenda.

## Dirección visual propuesta

- Tinta verde petróleo `#173D35`; acción primaria turquesa `#167C72`; selección menta `#E5F3EF`.
- Fondo marfil verdoso `#F6F8F6`, superficies blancas, bordes salvia `#D8E3DE` y texto secundario `#52645E`.
- Rojo apagado para error/destructivo y ámbar discreto para atención; siempre con texto o icono además del color.
- Esquinas moderadas, sombras casi imperceptibles, tipografía de sistema legible y espacios constantes. Sin gradientes ni decoración dental literal.

## Verificación

Probar rutas y roles existentes sin cambios funcionales; correr suite frontend y build; revisar visualmente 360, 768 y 1280 px; verificar navegación con teclado, foco visible, contraste WCAG AA y `prefers-reduced-motion`.
