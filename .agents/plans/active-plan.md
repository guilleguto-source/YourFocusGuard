# Plan Activo: Confirmación Escrita con Cuenta Regresiva (15s) y Diálogo de Aclaración

## Contexto Digerido
1. Confirmación explícita previa a inserción en agenda: propuesta formateada en lenguaje natural.
2. Botones interactivos [ ✅ Agendar (15s) ] y [ ❌ Cancelar ] con auto-aceptación si expiran los 15s.
3. Diálogo de aclaración cuando falten horas ("¿A qué hora te hago el acuerdo mañana?") o cálculo automático de fin (+1h) si falta duración.
4. Soporte sincronizado en Mascota Nativa (Tkinter), Widget Embebido (HTML/JS) y Web Dashboard.

## Archivos Afectados
- `adhd-assistant/app/router.py`: reglas de aclaración si falta hora + instrucción de duración en prompt.
- `adhd-assistant/app/server.py`: emisión de propuesta `confirmar_evento` + endpoints `/api/calendario/confirmar` y `/cancelar`.
- `adhd-assistant/app/ui/` (`app.js`, `style.css`): banner interactivo con countdown 15s.
- `YourFocusGuard/yourfocusguard/desktop_pet_native.py`: renderizado de botones de opción en burbuja + tick countdown 15s.
- `YourFocusGuard/yourfocusguard/panel_static/pet-widget.html`: soporte countdown 15s en widget embebido.
- `YourFocusGuard/yourfocusguard/panel.py`: propagación de `auto_confirmar_seg` en `pet_decir`.
- `YourFocusGuard/yourfocusguard/actions/groq_voice.py`: aclaración cuando falta hora y propuesta con 15s auto-confirm.

## Checklist de Despliegue
- [x] Implementar aclaraciones y guardarraíles en `router.py`.
- [x] Endpoints y propuesta en `server.py`.
- [x] Banner interactivo con temporizador en `app.js` y `style.css`.
- [x] Botones de confirmación y contador 15s en `desktop_pet_native.py`.
- [x] Soporte countdown en `pet-widget.html` y `panel.py`.
- [x] Diálogo de aclaración de voz en `groq_voice.py`.
- [x] Ejecutar suite de pruebas (101/101 OK).
- [x] Git commit y push.
