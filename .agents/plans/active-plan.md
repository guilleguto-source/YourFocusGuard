# Plan de Auditoría y Optimización /boost

## Contexto Digerido
- Auditoría profunda ejecutada con DeepInvestigator sobre ambos repositorios.
- Suites de pruebas verificadas en verde: 281/281 YourFocusGuard y 101/101 ADHD Assistant.
- Hallazgos detectados para resolución quirúrgica:
  1. Redundancia de código fantasma en `panel.py` (bloque `if 'mascota' in payload:` duplicado).
  2. Blindaje de `do_POST` en `panel.py` con `urlparse().path` ante posibles query strings.
  3. Soporte del comando `start_voice` en `/api/control` para que el botón `🎤` del widget web active el micrófono en memoria sin error 400.
  4. En `groq_voice.py::_auto_ejecutar()`, reemplazar el `sleep(15)` ciego por sondeo reactivo: si el usuario pulsa Cancelar se aborta de inmediato; si pulsa Agendar se ejecuta sin esperar los 15s.
  5. Inversión de parámetros `mascota / puerto` en `desktop_pet.py::__main__`.
  6. Limpieza de 137 archivos residuales de tests en `YourFocusGuard/_pytmp/` (8.9 MB) y `auth_url.txt`.

## Archivos Afectados
- `YourFocusGuard/yourfocusguard/panel.py`: eliminar bloque duplicado, blindar `do_POST` con `urlparse` y autorizar `start_voice` directo.
- `YourFocusGuard/yourfocusguard/actions/groq_voice.py`: hacer reactivo el guardarraíl de 15s con `pet_consumir_respuestas()`.
- `YourFocusGuard/yourfocusguard/desktop_pet.py`: alinear orden CLI `sys.argv[1]=mascota`, `sys.argv[2]=puerto`.
- Limpieza: remover carpeta `YourFocusGuard/_pytmp/` y `adhd-assistant/auth_url.txt`.

## Checklist de Despliegue
- [x] Limpiar bloque redundante en `panel.py`.
- [x] Aplicar `urlparse` en `do_POST` y despacho de `start_voice` en `panel.py`.
- [x] Implementar sondeo reactivo en `_auto_ejecutar()` de `groq_voice.py`.
- [x] Corregir orden de argumentos CLI en `desktop_pet.py`.
- [x] Unificar botones del widget (`pet-widget.html`) con la mascota nativa: `[✅ Sigo aquí] [⏸ Pausa 10 min] [📖 Estoy leyendo]` en 1 fila horizontal sin recortes.
- [x] Purgar archivos temporales residuales (`_pytmp/` y `auth_url.txt`).
- [x] Ejecutar ambas suites de pruebas (281/281 YourFocusGuard y 101/101 ADHD Assistant).
- [x] Reiniciar procesos silenciosos en segundo plano.
- [x] Git commit y push a `origin/main`.
