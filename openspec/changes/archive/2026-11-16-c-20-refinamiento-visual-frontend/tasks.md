# Tasks

## 1. Sistema visual compartido

- [x] 1.1 Auditar todas las rutas/pestañas, componentes y estilos actuales; registrar estados de carga, vacío, error, éxito y deshabilitado.
- [x] 1.2 Crear tokens CSS y estilos base accesibles para tipografía, canvas/superficies, controles, botones, foco, bordes y espaciado; validar contraste WCAG AA.
- [x] 1.3 Actualizar shell, navegación, login y componentes compartidos (formulario, tabla, modal, toast) con los tokens.

## 2. Aplicación por superficie

- [x] 2.1 Refinar agenda diaria/semanal y vistas de turnos sin cambiar sus interacciones ni densidad operativa.
- [x] 2.2 Refinar lista de pacientes y pestañas de ficha: HCE, odontograma, adjuntos, consentimientos y presupuestos.
- [x] 2.3 Refinar caja, reportes, reserva pública, portal del paciente y placeholders visibles.
- [x] 2.4 Unificar indicadores semánticos de estado; verificar que texto/icono complementen al color en todos los módulos.

## 3. Verificación

- [x] 3.1 Verificar visualmente rutas y estados principales en 360, 768 y 1280 px; comprobar zoom 200%, teclado, foco y `prefers-reduced-motion`. Verificación responsive a 180/360/768/1280 px sin overflow horizontal (180 px simula viewport de 360 px al 200%); foco de teclado visible y soporte de movimiento reducido confirmados.
- [x] 3.2 Ejecutar suite frontend y build; comprobar que rutas, guards, requests y flujos de dominio existentes siguen pasando. Suite: 27 archivos y 108 tests; build TypeScript/Vite de producción correcto.
