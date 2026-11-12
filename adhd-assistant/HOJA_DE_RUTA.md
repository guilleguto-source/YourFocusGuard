# Hoja de Ruta — Asistente TDAH

**Actualizado:** 12 de noviembre de 2026 · **Versión actual:** v0.12.0
**Estado:** 102/102 pruebas automáticas OK → listo para la fase MCP

---

## 1. Dónde estamos

| Versión | Tema | Estado |
| :--- | :--- | :--- |
| v0.9.0 | Migración desde YourFocusGuard (Groq qwen, OAuth, Vikunja REST, YouTube, panel web) | ✅ base |
| v0.9.1 | Voz neuronal edge-tts gratis + seguridad (CORS, token Vikunja a .env) | ✅ entregado |
| **v0.10** | **Consolidación:** limpieza Docker/Redis/código muerto + sync bidireccional tareas↔Google Calendar + fechas completas en alarmas | ✅ **hecho** |
| **v0.11** | **Memoria:** notas rápidas con búsqueda, memoria de conversación (contexto al LLM), briefing diario hablado | ✅ **hecho** |
| **v0.12** | **Prep MCP:** registro central de 12 herramientas con esquemas JSON, /api/salud, suite de 102 pruebas automáticas | ✅ **hecho** |
| v0.13 | **Fase MCP** (ver §4) | ⏭️ siguiente |

---

## 2. Qué aprendimos de los proyectos similares

(análisis de OpenJarvis y sus alternativas — qué sí adoptamos y qué no)

| Proyecto | Qué tiene de valioso | Decisión para nosotros |
| :--- | :--- | :--- |
| **OpenJarvis** | Local-first, "Intelligence Per Watt" (SLM en hardware modesto), extensiones Rust | **Parcial.** Su filosofía local coincide con nuestra historia (Groq gratis + edge-tts + cache). Pero cambiar a Ollama SLM hoy bajaría la calidad del router y añadiría 4-8 GB de peso: tu máquina ya tiene una rutina que funciona. Mantenemos la métrica "potencia por vatio" como CRITERIO de decisión (priorizar lo ligero y gratis), no como migración. |
| **Khoj** (38k⭐) | Second brain personal: notas + RAG + búsqueda semántica | **ADOPTADO (v0.11).** Es la pieza más TDAH-útil de todas: memoria externa que compensa el olvido. Implementamos la versión ligera: notas + búsqueda tolerante + briefing, SIN base vectorial (0 dependencias nuevas). Si algún día quieres búsqueda semántica real, Khoj demuestra que se puede; sería el paso v0.14+ con embeddings locales. |
| **Qwen-Agent** (17k⭐) | MCP como protocolo estándar de herramientas; agentes con modelos pequeños | **ADOPTADO (v0.12→v0.13).** Es exactamente nuestro siguiente paso: ya tenemos el registro de 12 herramientas con esquemas JSON idénticos a los que MCP exige. La diferencia clave: ellos exigen su framework; MCP es un estándar abierto que nos deja el motor que queramos (seguimos con Groq). |
| **OpenInterpreter** (68k⭐) | Ejecutar código/OS arbitrario por lenguaje natural | **NO adoptamos.** Peligroso para un asistente que se controla por voz: un STT mal transcrito podría ejecutar comandos destructivos. Nuestro dominio de acción es acotado a propósito (tareas/calendario/notas/audio). |
| **Agent Zero** (19k⭐) | Multi-agente que se programa a sí mismo | **NO por ahora.** Fascinante pero impredecible; un asistente TDAH necesita confiabilidad y respuestas rápidas, no agentes que improvisan. |
| **Jarvis Desktop** (2.2k⭐) | Hotkey global + dictado por voz en cualquier app | **Idea para más tarde.** El push-to-talk ya existe en nuestro panel; un hotkey global (tipo Ctrl+Shift+Espacio) sería el complemento natural cuando pasemos a app de escritorio (v0.14+). |

**Conclusión:** no copiamos ningún proyecto; tomamos de Khoj la memoria,
de Qwen-Agent el protocolo MCP, de OpenJarvis el criterio de ligereza, y
descartamos lo que pone en riesgo la confiabilidad.

---

## 3. Lo que ya está listo para MCP (v0.12)

1. `app/herramientas.py` — registro ÚNICO de las 12 herramientas:
   nombre, descripción, parámetros tipados y ejemplos.
2. `esquemas_mcp()` — las expone en el formato exacto del protocolo
   (name / description / inputSchema JSON Schema) → `GET /api/herramientas`.
3. `validar()` — validación de parámetros por herramienta.
4. El prompt del router ya se GENERA desde el registro (fuente única de
   verdad: añadir una herramienta = 1 entrada en el registro).
5. Suite de 102 pruebas que garantiza que nada se rompe en el camino.

---

## 4. Fase MCP (v0.13) — plan concreto

**¿Qué es MCP?** Model Context Protocol: un estándar abierto (de
Anthropic, adoptado también por Qwen-Agent, Cursor, etc.) para que
cualquier cliente de IA descubra y use herramientas de un servidor.
Traducción práctica: **tu asistente deja de vivir solo en el panel web** —
Claude Desktop, Qwen-Chat u otro cliente MCP podrían crear tus tareas,
consultar tus notas o pedir el briefing.

**Pasos:**

1. **Servidor MCP stdio** (`app/mcp_server.py`) con el SDK oficial
   (`pip install mcp`):
   - `ListTools` → devuelve `herramientas.esquemas_mcp()` (ya está hecho)
   - `CallTool(nombre, args)` → ejecuta la misma lógica que hoy usa
     `/api/chat` (reutiliza tasks_mgr, calendar, memoria, timer, audio)
   - Arranque: `python -m app.mcp_server`
2. **Herramientas expuestas inicialmente (8 de las 12):** tarea_crear,
   tarea_listar, tarea_completar, crear_evento, nota_crear, nota_buscar,
   briefing_diario, crear_alarma. (Las de audio quedan fuera al inicio:
   reproducir sonido no tiene sentido desde un cliente externo.)
3. **Registro en Claude Desktop** (`claude_desktop_config.json`):
   ```json
   { "mcpServers": { "asistente-tdah": {
       "command": "python",
       "args": ["-m", "app.mcp_server"],
       "cwd": "C:/ruta/a/adhd-assistant"
   } } }
   ```
4. **Pruebas:** extender `pruebas_automaticas.py` con la sección MCP
   (list_tools devuelve 8, call_tool tarea_crear funciona end-to-end).
5. **Documento:** `MCP.md` con instrucciones de conexión.

**Requisitos nuevos:** solo `pip install mcp` (~2 MB). Sin cuentas de
pago, sin API keys nuevas. El panel web sigue siendo la interfaz
principal; MCP es una puerta adicional.

---

## 5. Ideas futuras (post-MCP, sin compromiso)

- **v0.14:** hotkey global de dictado (idea de Jarvis Desktop) y/o
  búsqueda semántica local de notas con embeddings (idea de Khoj).
- **v0.15:** briefing automático a primera hora (tarea programada de
  Windows o arranque con el sistema).
- Reevaluar Ollama + SLM local SOLO si Groq cambia sus condiciones
  gratuitas (métrica OpenJarvis: mismo servicio, menos dependencia).
- Modo privado / registro local de actividad (pendiente heredado de
  YourFocusGuard v0.8.3).

---

## 6. Cómo verificar cada avance

Cada versión debe pasar `python pruebas_automaticas.py` en verde antes
de considerar el siguiente paso. La suite hace backup de tus datos y
usa el puerto 8799: puedes ejecutarla con tu servidor real andando.
