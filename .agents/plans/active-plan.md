# Plan Activo: Integración Asistente TDAH v0.12

## Contexto Digerido
Actualización desde v0.9 hacia v0.12 (paquete completo auditado con 102/102 tests OK).
1. Segundo cerebro (memoria persistente Khoj-style + briefing diario hablado).
2. Sync bidireccional Tareas ↔ Google Calendar (marcar completada borra evento).
3. Edge-TTS neuronal con pre-cache de frases fijas.
4. Registro MCP de 12 herramientas con esquemas JSON (`/api/herramientas`).
5. Endpoint y panel UI de diagnóstico `/api/salud`.
6. Limpieza controlada de código muerto heredado (Docker, Redis, stt/music dummies).

## Archivos Afectados
- **Nuevos en `adhd-assistant/`**: `app/memoria.py`, `app/herramientas.py`, `app/tts.py`, `app/utilidades.py`, `precache_tts.py`, `limpiar_residuos.py`, `pruebas_automaticas.py`, `LEEME.md`, `HOJA_DE_RUTA.md`.
- **Modificados**: `app/server.py`, `app/tasks_sync.py`, `app/google_calendar.py`, `app/router.py`, `app/timer.py`, `app/ui/` (`index.html`, `style.css`, `app.js`), `requirements.txt`, `config.json`, `.env.example`, `README.md`.
- **Eliminados (obsoletos)**: `docker-compose.yml`, `Dockerfile`, `app/stt.py`, `app/music.py`, `app/config.py`.
- **Preservados intactos**: `.env`, `credentials.json`, `token.json`, `data/tasks.json`.

## Checklist de Despliegue
- [x] Detener daemon actual de `server.py` (puerto 8765).
- [x] Respaldar credenciales y datos (`credentials.json`, `token.json`, `data/`).
- [x] Descomprimir y desplegar archivos de `adhd_assistant_v0.12` sobre `adhd-assistant/`.
- [x] Ejecutar `limpiar_residuos.py` para retirar Docker/Redis/stt/music obsoletos.
- [x] Instalar dependencias adicionales de `requirements.txt` (`edge-tts`).
- [x] Configurar `.env` con variables seguras (`GROQ_API_KEY`, `VIKUNJA_TOKEN`, `VIKUNJA_URL`).
- [x] Ejecutar `python pruebas_automaticas.py` (101/101 OK en entorno local).
- [x] Reiniciar daemon de `server.py` y verificar `/api/salud` (`http://localhost:8765`).
- [ ] Git commit y push a `https://github.com/guilleguto-source/YourFocusGuard.git`.
