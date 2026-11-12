# Asistente TDAH v0.12 — Proyecto completo

**Fecha:** 12 de noviembre de 2026
**Estado:** 102/102 pruebas automáticas OK (ver §5)

Este paquete contiene el **proyecto completo y actualizado** (no es un
parche parcial): reemplaza tu carpeta `adhd-assistant/` actual y suma
todo lo de v0.9.1 (voz neuronal edge-tts, seguridad CORS, token Vikunja
fuera del código).

---

## 1. Novedades por versión

### v0.10 — Consolidación y sincronización bidireccional
- **Sync bidireccional tareas ↔ Google Calendar** (`POST /api/sync/calendario`
  o botón 🔄 en el panel):
  - Completar una tarea con fecha **elimina su evento** del calendario
    (libera tu agenda automáticamente).
  - Tareas con fecha creadas sin conexión reciben su evento después
    (catch-up sync).
  - Si mueves o borras el evento **en Google**, la tarea local se
    actualiza o queda marcada como huérfana.
  - Los eventos del asistente llevan la etiqueta `[asistente-tdah]` para
    no tocar nunca tus otros eventos.
- **Fechas completas en las alarmas**: ahora suenan y se muestran como
  "jueves 12 de noviembre de 2026, 15:04" (antes solo HH:MM:SS y las de
  +24 h eran confusas).
- **`limpiar_residuos.py`**: borra Docker/Redis/código muerto de tu
  proyecto viejo (`docker-compose.yml`, `Dockerfile`, `redis-data/`,
  `app/stt.py`, `app/music.py`, `app/config.py`) con modo `--solo-ver`.
- El router ahora extrae **fecha límite opcional** para las tareas.

### v0.11 — Memoria y "segundo cerebro" (inspirado en Khoj)
- **Notas rápidas** (`app/memoria.py`): "anota que el wifi es 1234" →
  guardado. Búsqueda tolerante a acentos/mayúsculas: "¿qué anoté de la
  puerta?" encuentra "PUERTA". Panel nuevo "🧠 Mi Memoria" en la UI.
- **Memoria de conversación**: el asistente recuerda tus últimas 6
  órdenes y las inyecta al prompt de Groq (contexto para "y el viernes?",
  "recuérdame lo de ayer").
- **Briefing diario** (`GET /api/briefing` o botón ☀️): resumen hablado
  con fecha, eventos de hoy del calendario, tareas urgentes y notas del
  día. La voz neuronal lo lee por trozos automáticamente.
- Rotación automática: máx. 200 notas / 300 interacciones (configurable
  en `config.json` → `memoria`).

### v0.12 — Preparación MCP + diagnóstico + pruebas
- **Registro central de herramientas** (`app/herramientas.py`): las 12
  capacidades del asistente definidas UNA sola vez con esquemas JSON.
  El prompt del router se genera desde ahí, y `GET /api/herramientas`
  las expone **en formato MCP** (name/description/inputSchema).
- **`GET /api/salud`**: versión, voz (perfil + audios en caché), Groq,
  Calendar, Vikunja, tareas, notas, alarmas. Panel nuevo "🩺 Estado del
  Sistema" en la UI (se actualiza cada 60 s).
- **`pruebas_automaticas.py`**: 102 pruebas que validan todo el sistema
  sin tocar tus datos (backup/restore automático, puerto 8799).
  Durante el desarrollo encontró y corrigió 2 bugs reales:
  1. "ruido rosa" no activaba el generador (faltaba en los disparadores)
  2. "ruido rosa **para** leer" detenía el audio (el stop se detectaba
     con el substring "para" — bug latente desde v0.9)

---

## 2. Instalación (desde tu proyecto v0.9.x)

```bash
# 1) Haz copia de seguridad de tu carpeta adhd-assistant/ actual
#    (en especial: .env, credentials.json, token.json, data/)

# 2) Copia el contenido de esta carpeta DENTRO de tu proyecto,
#    reemplazando los archivos que ya existen (app/, config.json,
#    requirements.txt, etc.)

# 3) Limpia los residuos del proyecto viejo (Docker, Redis, stt/music/config)
python limpiar_residuos.py --solo-ver   # primero mira qué borraría
python limpiar_residuos.py              # borra de verdad

# 4) Instala dependencias (no hay nuevas respecto a v0.9.1)
pip install -r requirements.txt

# 5) Tu .env sigue igual (GROQ_API_KEY, VIKUNJA_TOKEN nuevo, ASISTENTE_VOZ)

# 6) Pre-graba las frases fijas (ahora 30, incluye memoria y briefing)
python precache_tts.py

# 7) Arranca
python app/server.py
#    Abre http://localhost:8765
```

**Qué NO incluye este paquete** (y no debe): `.env`, `credentials.json`,
`token.json`, `data/`. Los tuyos siguen funcionando igual.

---

## 3. Cómo usar lo nuevo

| Quiero... | Dilo así / hazlo |
| :--- | :--- |
| Guardar una nota | "anota que el código de la puerta es 1234" |
| Recuperarla | "qué anoté de la puerta" (voz o texto) |
| Resumen del día | "resumen del día" o botón ☀️ en el panel |
| Sincronizar calendario | botón 🔄 de la tarjeta de tareas |
| Ver qué funciona | panel 🩺 Estado del Sistema (o clic en la versión del header) |
| Buscar notas en el panel | caja de búsqueda de "Mi Memoria" (busca mientras escribes) |

---

## 4. Mapa de la API (todos verificados por la suite)

| Método | Ruta | Qué hace |
| :--- | :--- | :--- |
| GET | `/api/salud` | Diagnóstico integral (v0.12) |
| GET | `/api/herramientas` | Las 12 herramientas en formato MCP (v0.12) |
| GET | `/api/briefing` | Resumen del día en texto (v0.11) |
| GET/POST/DELETE | `/api/notas` | Notas: listar/buscar, crear, borrar (v0.11) |
| POST | `/api/sync/calendario` | Sync bidireccional tareas↔Calendar (v0.10) |
| GET | `/api/calendario/eventos?dias=N` | Próximos eventos (v0.10) |
| GET/POST | `/api/tasks` · `/api/tasks/complete` | Tareas (Vikunja + local + Calendar) |
| POST | `/api/chat` | Órdenes en lenguaje natural |
| GET | `/api/timers` · `/api/timers/announce` | Alarmas activas / vencidas por anunciar |
| GET | `/api/tts?text=...&perfil=...` · `/api/tts/voices` | Voz neuronal (hasta 1000 caracteres) |
| POST | `/api/audio/youtube` · GET `/api/audio/status` | Audio y ruido |

---

## 5. Verificación (sandbox, 12-nov-2026)

```
python pruebas_automaticas.py
→ 102 OK · 0 FALLOS · 0 omitidos / 102 pruebas
```

Cubre: sintaxis de los 11 módulos, registro MCP, utilidades de fecha en
español, 14 reglas rápidas del router, memoria (crear/buscar/borrar/
contexto), timers end-to-end, calendario sin credenciales, y 35 pruebas
HTTP incluyendo CORS (evil.com → 403) y el ciclo completo de notas,
tareas, alarmas y TTS.

Ejecútalo en tu máquina también: `python pruebas_automaticas.py`
(usa el puerto 8799 y restaura tus datos al terminar).

---

## 6. Problemas conocidos / notas

- La primera síntesis de una frase nueva tarda ~1 s (luego queda en
  caché y sale en 0 ms). Sin internet, la UI usa la voz del navegador.
- `sincronizar_calendario` solo procesa tareas del cache local (las
  creadas por el asistente); no toca tareas creadas a mano en Vikunja.
- Si cambias el puerto con `ASISTENTE_PUERTO`, el panel y la API deben
  usar el mismo puerto (la seguridad de origen lo exige).
- Siguiente fase: **MCP** — ver `HOJA_DE_RUTA.md`.
