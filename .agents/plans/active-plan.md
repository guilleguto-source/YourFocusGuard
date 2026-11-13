# Plan de Corrección: Botones Dinámicos (+5m), Micrófono Compacto y Solución 404

## Contexto Digerido
1. **Error 404 en el Panel Web (`Error response 404`):**
   - `panel.py` compara estrictamente `self.path == "/pet-widget.html"`. Al agregarse `?v=1.0.3` en `index.html`, no coincidió y lanzó 404.
   - Solución: parsear con `urllib.parse.urlparse(self.path).path` para admitir query params de caché.
2. **Botón Micrófono:**
   - Quitar la palabra "Hablar" y dejar únicamente el icono `🎤` en un botón píldora compacto central.
3. **Botones de Pausa y Continuar con Acumulación de +5 Minutos:**
   - Botón izquierdo: `⏸ +5m` (suma 5 minutos por cada clic: 5m, 10m, 15m... y confirma: "Pausa de X min activa").
   - Botón derecho: `▶ +5m` (suma 5 minutos por cada clic: +5m, +10m, +15m... y confirma: "+X min de foco añadidos").
4. **Corte de botones y espaciado al cambiar de tamaño:**
   - En `_cambiar_tamaño`, redibujar inmediatamente la burbuja y botones (`_mostrar_burbuja`).
   - Fijar un ancho mínimo seguro (`ancho_win >= 210px`) para evitar que el tercer botón se corte en tamaño "pequeño".
   - Ajustar el espaciado vertical entre botones y la mascota.

## Archivos Afectados
- `YourFocusGuard/yourfocusguard/panel.py`: parsear `urlparse(self.path).path` en `do_GET` para eliminar el error 404 en `/pet-widget.html`.
- `YourFocusGuard/yourfocusguard/desktop_pet_native.py`:
  - Botones estándar: `[⏸ +5m]` (acumulativo), `[🎤]` (solo icono), `[▶ +5m]` (acumulativo).
  - Confirmación inmediata en burbuja con los minutos totales acumulados.
  - Redibujado automático en `_cambiar_tamaño` con ancho mínimo seguro contra recortes.
- `YourFocusGuard/yourfocusguard/panel_static/pet-widget.html`: reflejar los mismos botones `[⏸ +5m]`, `[🎤]`, `[▶ +5m]` acumulativos.

## Checklist de Despliegue
- [x] Modificar `panel.py` para normalizar rutas estáticas sin query params (resuelve 404).
- [x] Modificar `desktop_pet_native.py` con botones acumulativos (+5m), micro solo `🎤` y redraw al redimensionar.
- [x] Modificar `pet-widget.html` con la misma lógica de botones y acumulación de +5m.
- [x] Reiniciar procesos silenciosos para validar visualmente.
- [x] Ejecutar suites de pruebas (281/281 OK).
- [x] Git commit y push.
