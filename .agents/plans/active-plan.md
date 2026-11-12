# Plan Activo: Corrección UI Mascota Nativa y Guardarraíles de Agenda

## Contexto Digerido
1. Mascota flotante de escritorio (`desktop_pet_native.py`) adaptada con botones píldora modernos (paleta dashboard), bordes redondeados y microinteracciones hover.
2. Burbujas con auto-altura y cero scrollbars en mascota nativa y widget embebido (`pet-widget.html`).
3. Temporizador de 30s implementado: tras 30s los textos largos se contraen a una cápsula compacta con resumen.
4. Falsos positivos de agendamiento erradicados en `vikunja.py` (filtro de negaciones y exigencia imperativa) y `router.py` (guardarraíl de charla ante dudas/negaciones).

## Archivos Afectados
- `YourFocusGuard/yourfocusguard/desktop_pet_native.py`: botones modernos estilo dashboard, burbuja autoajustable sin scroll, temporizador 30s con texto resumen.
- `YourFocusGuard/yourfocusguard/panel_static/pet-widget.html`: eliminación de scrollbar, flex autoajustable y timer 30s a resumen.
- `YourFocusGuard/yourfocusguard/integrations/vikunja.py`: regex imperativa estricta en `_PATRONES_AGENDA` con exclusión de negaciones.
- `adhd-assistant/app/router.py`: regla estricta anti-agendamiento sin orden explícita y descarte de negaciones.

## Checklist de Despliegue
- [x] Refactorizar `desktop_pet_native.py` (estilos canvas, auto-altura, auto-colapso 30s).
- [x] Refactorizar `pet-widget.html` (CSS sin overflow/scrollbar, JS timer 30s).
- [x] Endurecer `vikunja.py` contra falsos positivos de agendamiento.
- [x] Endurecer prompt y reglas de `router.py` para `crear_evento`.
- [x] Probar visualmente renderizado de mascota y probar frases trampa en router.
- [x] Ejecutar suite de pruebas (101/101 OK).
- [x] Git commit y push.
