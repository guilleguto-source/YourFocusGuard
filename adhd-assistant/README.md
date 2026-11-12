# Asistente TDAH v0.12 — Core

Asistente inteligente de baja latencia optimizado para personas con TDAH.

Para la documentación detallada de la versión 0.12, consulta [LEEME.md](LEEME.md) y la [HOJA_DE_RUTA.md](HOJA_DE_RUTA.md).

## Capacidades Principales
- **Segundo Cerebro**: Notas rápidas y memoria conversacional multi-turno con Groq (`app/memoria.py`).
- **Sincronización Bidireccional**: Tareas ↔ Google Calendar con etiquetas automáticas (`[asistente-tdah]`).
- **Voz Neuronal**: Integración con Microsoft Edge TTS y pre-caché de frases frecuentes (`app/tts.py`).
- **Preparación MCP**: Registro de 12 herramientas estandarizadas (`app/herramientas.py`).
- **Observabilidad**: Diagnóstico en tiempo real en `/api/salud`.
- **Suite de Pruebas**: 102 tests automatizados con verificación hermética (`pruebas_automaticas.py`).

## Inicio Rápido
1. Instala dependencias: `pip install -r requirements.txt`
2. Configura tu `.env` (ver `.env.example`)
3. Inicia el servidor: `python app/server.py`
4. Abre tu navegador en `http://localhost:8765`
