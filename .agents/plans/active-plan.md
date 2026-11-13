# Plan de Implementación: Lanzador Silencioso Independiente y Accesos Directos

## Contexto Digerido
- El usuario solicita detener los procesos actuales dentro de Antigravity.
- Desea que ambos servicios (`adhd-assistant` en :8765 y `YourFocusGuard` con la mascota en :8756) funcionen de forma independiente de Antigravity.
- Cero ventanas de consola visibles (modo totalmente silencioso con `pythonw` y `.vbs`).
- Accesos directos limpios y actualizados en el Escritorio (`C:\Users\Guill\Desktop`), eliminando los anteriores.

## Archivos Afectados / Creados
- `iniciar_asistente.bat` (nuevo en raíz): arranque con `pythonw.exe` de `adhd-assistant/app/server.py` y `YourFocusGuard/run.py start`.
- `iniciar_silencioso.vbs` (nuevo en raíz): wrapper VBScript (`windowStyle=0`) para ejecutar `iniciar_asistente.bat` sin ventana de consola.
- `detener_asistente.bat` (nuevo en raíz): terminación limpia de ambos servicios.
- `detener_silencioso.vbs` (nuevo en raíz): wrapper VBScript silencioso para detención.
- `C:\Users\Guill\Desktop\Iniciar Asistente TDAH.lnk`: acceso directo en el escritorio.
- `C:\Users\Guill\Desktop\Detener Asistente TDAH.lnk`: acceso directo de parada.

## Checklist de Despliegue
- [ ] Detener procesos activos en Antigravity (`task-868` y `task-1052`).
- [ ] Crear scripts de inicio silencioso unificado (`.bat` y `.vbs`).
- [ ] Crear scripts de detención silenciosa unificada (`.bat` y `.vbs`).
- [ ] Eliminar accesos directos obsoletos en `C:\Users\Guill\Desktop`.
- [ ] Crear nuevos accesos directos en el Escritorio apuntando a los lanzadores silenciosos.
- [ ] Ejecutar el lanzador silencioso para verificar arranque independiente y ausencia de consolas.
