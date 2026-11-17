# Plan: Doble Widget Móvil (Panel Tareas + Mascota Móvil) y Selector de Destino

## Contexto
El usuario desea conservar el widget táctil actual (tareas, alarmas, briefing) y añadir un **segundo widget dedicado a la mascota** para el celular (Nubia Z17 Lite). La mascota tendrá sus botones (+5m, mic, seguir, burbuja), un tamaño fijo adaptado a la pantalla del móvil y una animación con 50% de movimiento del original. Además, en el dashboard de la PC se podrá elegir el destino de la mascota: solo PC, solo celular o ambos.

## Arquitectura de los 2 Widgets
1. **Widget 1 (Panel Productivo)**: `http://localhost:8765/widget`
   - Conserva la vista actual: reloj, briefing, alarmas rápidas, tareas y notas.
   - Pestaña/botón superior para alternar con la mascota.
2. **Widget 2 (Mascota Móvil)**: `http://localhost:8765/widget-mascota`
   - Vista dedicada y limpia de la mascota activa (Einstein u otra elegida en settings).
   - Animación viva con 50% de movimiento (CSS bobbing suave).
   - Barra de control idéntica a la PC: `[ ⏸ +5m ]`, `[ 🎤 ]`, `[ ▶ +5m ]`.
   - Burbuja reactiva a preguntas y desvíos (`[ Sigo aquí ]`, `[ Pausa 10m ]`, `[ Leyendo ]`).
   - Pestaña superior para volver al panel productivo.
3. **Selector de Destino en Dashboard (`panel_static/index.html`)**:
   - Ajuste: "Mostrar mascota en": `🖥️ Pantalla de la PC` | `📱 Celular` | `🖥️📱 Ambos`.
   - Controla si `desktop_pet_native.py` se muestra/oculta en Windows sin afectar el servicio del celular.

## Archivos Afectados
- `adhd-assistant/app/ui/widget-mascota.html` (nuevo: UI dedicada de la mascota para el celular)
- `adhd-assistant/app/ui/widget-mascota.css` (nuevo: estilos, escala fija y keyframes 50% movimiento)
- `adhd-assistant/app/ui/widget-mascota.js` (nuevo: polling de estado, burbuja y control de acciones)
- `adhd-assistant/app/ui/widget.html` (navegación para alternar entre Panel y Mascota)
- `adhd-assistant/app/server.py` (ruta `/widget-mascota` y proxy/sync de estado con YourFocusGuard)
- `YourFocusGuard/yourfocusguard/panel_static/index.html` (selector de destino de mascota en Dashboard)
- `YourFocusGuard/yourfocusguard/panel_static/aplicacion.js` (persistencia del selector y control de ventana PC)
- `YourFocusGuard/yourfocusguard/config.py` y `config/user.toml` (campo `destino_mascota: "pc" | "celular" | "ambos"`)

## Checklist de Implementación
- [ ] 1. Crear `widget-mascota.html/.css/.js` en `adhd-assistant/app/ui/` con escala óptima y animación viva 50%.
- [ ] 2. Añadir ruta `/widget-mascota` en `server.py` sirviendo los assets y comunicando eventos con el puerto 8756.
- [ ] 3. Añadir barra de navegación simple `[ 📱 Panel ] [ 🐶 Mascota ]` en ambos widgets.
- [ ] 4. Añadir selector "Mostrar mascota en" en `index.html` del panel de settings.
- [ ] 5. Ajustar lógica en `desktop_pet_native.py` para ocultar la ventana en Windows si el destino es "solo celular".
- [ ] 6. Validar pruebas unitarias y funcionamiento de ambos widgets.
