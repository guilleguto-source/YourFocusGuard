# Paquete de Auditoría Preparado: ADHD Assistant v0.9.0

**Archivo generado:** [`adhd_assistant_auditoria.zip`](file:///c:/Users/Guill/Documents/antigravity/ADHD%20Assistant/adhd_assistant_auditoria.zip) (Peso: ~29 KB)  
**Documento de auditoría:** [`README_AUDITORIA_ADHD.md`](file:///c:/Users/Guill/Documents/antigravity/ADHD%20Assistant/README_AUDITORIA_ADHD.md)

---

### Manifiesto de Inclusiones y Exclusiones para el Auditor

1. **Incluido en el paquete (~29 KB):**
   - Código fuente completo: `google_calendar.py`, `tasks_sync.py`, `audio_engine.py`, `timer.py`, `router.py`, `server.py`, `main.py`.
   - Frontend Glassmorphic: `ui/index.html`, `ui/style.css`, `ui/app.js`.
   - Manifiesto técnico `README_AUDITORIA_ADHD.md` con endpoints y diagramas de flujo.
   - Configuración Docker y dependencias: `config.json`, `docker-compose.yml`, `requirements.txt`.

2. **Excluido intencionalmente (con justificación documentada):**
   - **Bases de datos binarias SQLite (`*.db`, `-wal`, `-shm`):** Excluidas por peso (~8 MB) y privacidad; el esquema se inicializa solo.
   - **Logs históricos (`agente.log`):** Excluidos por peso (~4 MB); la app genera logs limpios en tiempo de ejecución.
   - **Caché bytecode (`__pycache__/*.pyc` y `.pytest_cache`):** Excluidos por redundancia.
   - **Archivos de medios de prueba (`test_mascota.mp3`, capturas PNG):** Excluidos por ser binarios estáticos no esenciales para la lógica.
   - **Tokens de sesión vivos (`token.json`, `.env`):** Excluidos por seguridad de credenciales; se incluyen plantillas.
