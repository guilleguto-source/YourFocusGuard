# Plan Activo: Corrección de Formato de Botones y Estilo Visual de la Mascota

## Contexto Digerido
1. La mascota nativa y el widget embebido recibían tuplas `[clave, etiqueta]` (ej. `("sigo", "Sigo aquí")`).
2. Se renderizaba el array crudo en el texto de los botones (`['sigo', 'Sigo aquí']` y `sigo,Sigo aquí`) provocando desbordes y aspecto tosco.
3. No se requiere reiniciar la máquina; solo desempaquetar la etiqueta legible (`Sigo aquí`, `Pausa 10 min`) y reiniciar el proceso de la mascota.

## Archivos Afectados
- `YourFocusGuard/yourfocusguard/desktop_pet_native.py`: desempaquetado de tuplas `(clave, etiqueta)`, renderizado de etiqueta limpia y ajuste de estilo píldora.
- `YourFocusGuard/yourfocusguard/panel_static/pet-widget.html`: desempaquetado de array en JS para mostrar solo la etiqueta.

## Checklist de Despliegue
- [x] Modificar `desktop_pet_native.py` para parsear tuplas/listas de opciones (soporte 2 y 3 botones limpios).
- [x] Modificar `pet-widget.html` para parsear tuplas/listas de opciones y eliminar scroll con `overflow: hidden !important`.
- [x] Ajustar regex de Vikunja para intenciones tipo `guardar en vikunja`.
- [x] Detener procesos `pythonw` antiguos y relanzar el agente y mascota nativa.
- [x] Validar suites de pruebas: 281/281 OK en YourFocusGuard y 101/101 OK en adhd-assistant.
- [x] Git commit y push a `origin/main` (`5787bf8`).
