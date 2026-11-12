# Asistente TDAH (Ligero, Docker + Python)

Asistente inteligente simple optimizado para personas con TDAH:
- Baja latencia: respuestas rápidas con Groq (Llama-3 8B)
- Multi-API: usa Groq para charla rápida y Gemini para calendario/música
- Acciones: crea eventos en Google Calendar y reproduce música en Spotify
- Voz: incluye Faster-Whisper para STT (opcional)

## Uso rápido

1. Copia .env.example a .env y llena tus claves API.
2. docker-compose up --build
3. docker-compose run --rm adhd-assistant python app/main.py

## Enrutamiento

| Intención | API | Acción |
|-----------|-----|--------|
| Calendario | Gemini 1.5 Flash | calendar.create_event |
| Música | Gemini 1.5 Flash | music.play_track |
| Charla | Groq Llama-3 8B | Respuesta directa |

Puedes cambiar las reglas editando config.json.