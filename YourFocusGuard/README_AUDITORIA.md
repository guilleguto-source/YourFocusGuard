# YourFocusGuard — Documento de Auditoría y Registro de Correcciones

**Versión del paquete:** v0.8.3-auditoría
**Fecha de generación:** 10 de noviembre de 2026
**Destinatario:** Auditor / Revisor de código externo
**Entorno operativo:** Windows 10/11 (Python 3.11 o 3.12)
**Suite de pruebas verificada:** 256 passed, 0 failed (en Windows y en Linux)

> Este documento sustituye por completo a la versión anterior del README de
> auditoría (v0.8.2-audit), que describía una arquitectura inexacta (FastAPI,
> Pydantic, módulos `state.py`/`groq_client.py`/`stt.py`/`database.py` que no
> existen en el código). Todo lo que hay aquí abajo está verificado contra el
> código real, con archivo y línea.

---

## 1. Resumen ejecutivo

**YourFocusGuard** es un agente local de acompañamiento para personas con
**TDAH** que vigila la ventana activa de Windows, calcula la deriva de foco y
de bajo nivel (Win32), regaña de forma gradual y no punitiva, y conversa por
voz. Principios de diseño: **privacidad por defecto** (sin capturas de
pantalla, sin teclado grabado, cámara opt-in, voz opt-in), **degradación
silenciosa** (cada dependencia opcional puede faltar sin romper el agente) y
**modo privado absoluto** (cero nube, cero micrófono).

Componentes reales:

1. **Centinela Win32** (`engine.py`, `session_guard.py`, `capture/`):
   `GetForegroundWindow` + `GetLastInputInfo` + enum de ventanas visibles.
   Sin pulsaciones de teclado ni capturas.
2. **Mascota flotante nativa** (`desktop_pet_native.py`, Tkinter transparente
   con spritesheet animado, botones `[⏸ 10m] [▶ +15m] [🎤 Hablar]` y menú
   contextual), más la mascota clásica tkinter (`mascota.py`) como respaldo.
3. **Panel web local** (`panel.py` sobre `http.server` de la stdlib, solo
   `127.0.0.1:8756`): REST + estado en vivo, con validación de Origin y
   contención de rutas.
4. **Voz con Groq** (`actions/groq_voice.py`): STT Whisper
   (`whisper-large-v3-turbo`) + LLM (`llama-3.3-70b-versatile` con fallback) +
   TTS neuronal local con edge-tts (`actions/tts.py`). Soporta LLM local vía
   Ollama/LM Studio.
5. **Desacoplamiento** (`core/events.py`, pub/sub en memoria) y **comandos
   externos** (`core/commands.py`, `control.json`).
6. **Persistencia** (`storage/db.py`, SQLite con WAL, poda a 180 días).

---

## 2. Manifiesto de inclusiones y exclusiones

**Incluido (≈2,9 MB):** código completo (`yourfocusguard/`, `run.py`), suite
de 256 tests (`tests/`), configuración de fábrica (`config/`), spritesheet de
la mascota por defecto (`einstein`) y documentación.

**Excluido, y por qué:**

| Excluido | Motivo |
|---|---|
| 50+ spritesheets de mascotas secundarias (~150 MB) | Peso; el catálogo se resuelve dinámicamente desde disco |
| Bases SQLite (`*.db`, `-wal`, `-shm`) | Privacidad (métricas y nombres de ventana) |
| Logs (`data/logs/`) | Privacidad y peso |
| `.env` real | Credenciales; se provee `.env.example` |
| `__pycache__`, `.pytest_cache`, `.venv` | Artefactos locales |

> Nota honesta: la `chrome_extension/` de la v0.8.0 no está incluida en este
> paquete de auditoría. Verificar antes de publicar si fue exclusión
> deliberada o se perdió al empaquetar (no aparece mencionada en la documentación).

---

## 3. Despliegue para el auditor

```powershell
# 1. Entorno
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 2. Configuración de prueba (sin claves reales)
Copy-Item .env.example .env
# Para probar voz, inyecta tu GROQ_API_KEY en .env (la Suite NO la necesita)

# 3. Suite completa (esperado: 256 passed, 0 failed)
$env:PYTHONPATH="."
python -m pytest tests -q

# 4. Arranque
python run.py start          # agente + panel + mascota → http://127.0.0.1:8756
python run.py status
python run.py stop
```

Reproducción de las pruebas de seguridad (sección 6), desde PowerShell con
curl.exe (usa `--path-as-is` para no normalizar el traversal):

```powershell
# C-01 · Path traversal → esperado 403 (antes devolvía el archivo, HTTP 200)
curl.exe --path-as-is -s -o NUL -w "%{http_code}" "http://127.0.0.1:8756/pets/../../run.py"

# C-02 · CSRF con Origin externo → esperado 403
curl.exe -s -X POST "http://127.0.0.1:8756/api/control" -H "Content-Type: text/plain" -H "Origin: http://ejemplo-malicioso.com" -d "{\"cmd\":\"pause\",\"minutos\":10}"
```

La corrección C-10/C-11 (modo privado) se verifica con la suite
(`pytest tests/test_privacidad_voz.py -v`) y en vivo: escribe
`{"cmd":"privado","valor":true}` en `data/control.json` y comprueba en
`data/logs/agente.log` el mensaje *"Modo privado activo: omitiendo captura de
voz hacia Groq"* al dispararse un aviso N3.

---

## 4. Arquitectura real de módulos

```text
YourFocusGuard/
├── run.py                      # CLI (25 comandos; montaje de agente/panel/voz)
├── yourfocusguard/
│   ├── config.py               # dataclasses + TOML por capas + recarga en caliente (SIN Pydantic)
│   ├── engine.py               # bucle, estados, escalera, Pomodoro, presencia, refuerzo
│   ├── session_guard.py        # reglas R1/R2 por predicados (primer plano + idle)
│   ├── vigilante.py            # prohibiciones con presupuesto diario
│   ├── workflow_groups.py      # tolerancia a flujos vinculados (v0.8.0)
│   ├── panel.py                # servidor http.server (127.0.0.1), REST + assets
│   ├── core/
│   │   ├── events.py           # pub/sub en memoria (desacopla actions → UI)
│   │   └── commands.py         # CommandProcessor: control.json → motor
│   ├── actions/                # notifier, tts (edge-tts), groq_voice, sound, toast,
│   │                           # concentracion (hosts+audio), escalation, window_actions
│   ├── avatar/                 # interfaz Avatar + factory + openpets IPC + focus_bridge
│   ├── capture/                # window_info, idle, camera (opt-in), presencia (opt-in)
│   ├── brain/                  # router nube/local, gemini/openai, heurística local
│   ├── storage/db.py           # SQLite WAL + migraciones (no hay "database.py")
│   ├── desktop_pet.py          # lanzador subprocess de la mascota nativa
│   ├── desktop_pet_native.py   # mascota Tkinter transparente + botones + menú
│   ├── pet_sprite_player.py    # recorte de spritesheet .webp
│   ├── mascota.py              # mascota clásica tkinter (respaldo)
│   └── panel_static/           # index.html, estilos.css, aplicacion.js, pet-widget.html
└── tests/                      # 26 módulos, 256 tests, aislados en _pytmp/casos
```

**Nota de corrección documental:** la versión anterior de este README citaba
"FastAPI + SSE", "Pydantic", `state.py`, `groq_client.py`, `stt.py` y
`database.py`. Ninguno de esos módulos o dependencias existen en el proyecto.
El panel es `http.server.ThreadingHTTPServer` (`panel.py:24`), la
configuración es `dataclasses` + TOML manual, la voz vive en
`actions/groq_voice.py` y la base en `storage/db.py`.

---

## 5. Registro detallado de correcciones

Convención: cada corrección lleva **ID, severidad, dónde estaba el defecto,
por qué era un problema, la corrección aplicada (antes → después) y cómo se
verifica**. Bloque A = aplicadas por el equipo en v0.8.2 (ronda de auditoría
externa 1, verificadas hoy por el auditor). Bloque B = aplicadas en v0.8.3
(ronda 2, la presente). Bloque C = hallazgos aceptados como pendientes.

### Bloque A — correcciones de la v0.8.2 (verificadas por el auditor en este paquete)

**C-01 · Path traversal en el servicio de assets `/pets/`** — *Alta — ✅ corregida*
- **Defecto:** `panel.py` construía `ruta = STATIC_DIR / "pets" / Path(*partes[1:])`
  sin contención. `GET /pets/../../../run.py` devolvía **HTTP 200 con el
  archivo completo**, alcanzando también `.env` (con la clave Groq) y
  `config/user.toml`. Al ser localhost, cualquier página abierta en el
  navegador podía leerlos con `fetch` (combinado con C-02, sin preflight).
- **Corrección:** resolución y doble contención
  (`panel.py:601-621`):
  ```python
  pets_dir = (STATIC_DIR / "pets").resolve()
  ruta = (pets_dir / sub).resolve()
  if not ruta.is_relative_to(pets_dir):
      self.send_error(403, "Acceso denegado"); return
  ```
  El fallback por glob de spritesheet aplica la misma contención, y la
  decisión final de lectura re-verifica `ruta.is_relative_to(pets_dir)`.
- **Verificación:** comando curl de la sección 3 → `403`.

**C-02 · CSRF en `/api/*` (sin validación de Origin)** — *Alta — ✅ corregida*
- **Defecto:** `POST /api/control` aceptaba `Content-Type: text/plain` con
  cuerpo JSON; al ser "simple request" sin preflight CORS, una web externa
  podía pausar/detener el agente o activar/desactivar el modo privado.
- **Corrección:** `panel.py:659-667` valida el header `Origin` contra lista
  blanca (`http://127.0.0.1:<puerto>`); cualquier otro → `403 {"ok": false,
  "error": "Origin no permitido"}`.
- **Verificación:** comando curl de la sección 3 → `403`.

**C-03 · `tts.cerrar()` no existía (apagado sucio)** — *Media — ✅ corregida*
- **Defecto:** `notifier.py` llamaba `tts.cerrar()` al apagar el agente, pero
  el módulo solo define `parar()`. Cada apagado lanzaba `AttributeError`,
  tragado por el `except Exception` del engine, y el hilo de voz quedaba sin
  detener limpio (la mascota podía seguir hablando tras `run.py stop`).
- **Corrección:** `notifier.py:72` → `tts.parar()`.

**C-04 · Hosts sin red de seguridad (bloqueo permanente tras crash)** — *Alta — ✅ corregida*
- **Defecto:** el modo concentración editaba `C:\Windows\...\etc\hosts` con
  escritura atómica pero sin marcadores ni limpieza de arranque: si el proceso
  moría con la sesión activa, los dominios quedaban bloqueados para siempre.
- **Corrección:** el bloque editado queda acotado entre marcadores
  `# BEGIN YourFocusGuard (Concentracion)` / `# END ...`
  (`actions/concentracion.py:64-65`), lo que permite restaurar con exactitud
  y detectar restos huérfanos.

**C-05 · 3 tests fallaban fuera de Windows** — *Baja — ✅ corregida*
- **Defecto:** `tests/test_concentracion.py` mockeaba `_leer_hosts`/
  `_escribir_hosts` pero no `_IS_WINDOWS`; en Linux/macOS la suite era roja
  (235/238) y ocultaba regresiones reales.
- **Corrección:** parcheo explícito de `_IS_WINDOWS = True` en los 3 tests
  (líneas 47, 75, 99). Suite 100 % verde multiplataforma.

**C-06 · Instalación limpia sin voz + documentación de credenciales** — *Alta — ✅ corregida*
- **Defecto:** `groq_voice.py` importa `sounddevice`, `scipy` y `numpy`, que
  **no estaban** en `requirements.txt` (la voz fallaba en una instalación
  nueva); `.env.example` no mencionaba `GROQ_API_KEY` (la única clave que la
  instalación real usa); `pyttsx3` quedó como dependencia huérfana.
- **Corrección:** `requirements.txt` con `sounddevice>=0.4.6`, `scipy>=1.13.0`,
  `numpy>=1.26.0`; `pyttsx3` retirado; `.env.example` con entrada Groq y URL
  de consola.

**C-07 · Versión dispersa en 4 lugares** — *Media — ✅ corregida*
- **Defecto:** `__init__.py` = 0.8.0, docstrings/`USER_AGENT` = 0.8.2,
  CHANGELOG parado en 0.7.0, ESPECIFICACIONES en 0.7.1.
- **Corrección:** única fuente en `yourfocusguard/__init__.py::__version__`,
  consumida por `USER_AGENT = f"YourFocusGuard/{__version__}"`; CHANGELOG y
  ESPECIFICACIONES actualizados a 0.8.0/0.8.2.

**C-08 · `FocusBridge` crashearía al usarse (inyección ausente)** — *Media — ✅ corregida*
- **Defecto:** el puente OpenPets se construía sin `sesion` ni referencia al
  agente; `focus.start_session` crashearía en `self.sesion.iniciar` y
  `_cmd_pause/resume/sigo` serían no-ops.
- **Corrección:** el engine inyecta ambas dependencias tras construirlo
  (`engine.py:186-187`: `focus_bridge.sesion = self.guardia`,
  `focus_bridge.agente_ref = lambda: self`).

**C-09 · Desacoplamiento y extracción del procesador de comandos** — *Mejora estructural — ✅ aplicada*
- **Antes:** `actions/groq_voice.py` y `actions/tts.py` importaban el panel web
  (capa de acciones → capa de UI, acoplamiento inverso) y el procesamiento de
  `control.json` vivía dentro del engine.
- **Corrección:** nuevo paquete `yourfocusguard/core/`:
  - `events.py`: pub/sub en memoria (`subscribe/publish`, eventos
    `pet.say`, `pet.reaction`, `user.voice_response`, `api.consumo`). Las
    capas de acciones publican; el panel y la mascota se suscriben.
  - `commands.py`: `CommandProcessor` cableado en `engine.py:51,188`.

**C-09b · Deduplicación parcial del arranque** — *Media — ⚠️ parcial*
- `_construir_nube` (`run.py:144`) unifica el montaje del cerebro; `cmd_auto`
  sigue siendo una función propia pero ya no duplica el bloque completo
  (1.009 → 972 líneas). Pendiente consolidar del todo (bloque C).

### Bloque B — correcciones aplicadas en la v0.8.3 (esta ronda)

**C-10 · El candado de micrófono en modo privado era decorativo** — *Alta (privacidad) — ✅ corregida*
- **Defecto:** `notifier.py:45` (v0.8.2) leía
  `getattr(self.cfg.agente, "modo_privado", False)`, pero `AgenteCfg`
  (`config.py:35-38`) solo define `perfil`, `maquina` y `prompt_id`: **el
  atributo no existe** y `getattr` devolvía siempre `False`. Resultado: con el
  modo privado activado, tras cada aviso N3 se abría el micrófono y el
  audio/texto se enviaba a Groq (Whisper + LLM) — justo lo contrario de la
  promesa "cero nube" del modo privado.
- **Corrección** (`notifier.py:44-51`):
  ```python
  # antes (roto):
  if getattr(self.cfg.agente, "modo_privado", False):   # atributo inexistente
  # después:
  if getattr(self.cfg, "modo_privado", False):          # bandera real de nivel superior
  ```
  La bandera real es `Config.modo_privado` (`config.py:359`), la que escriben
  `load_config(..., modo_privado=...)`, el flag `--privado` y el comando
  `privado` de `CommandProcessor` (`core/commands.py:85`).
- **Comportamiento con modo privado:** el TTS local (voz de la mascota) sigue
  sonando si está habilitado — es síntesis local, no nube — pero **no se abre
  el micrófono y no sale ningún byte a la red**.

**C-11 · Dos candados muertos en el engine (pregunta contextual y refuerzo positivo)** — *Media — ✅ corregida*
- **Defecto:** `engine.py:1459` y `engine.py:1490` (v0.8.2) leían
  `getattr(self, "modo_privado", False)`: un atributo del engine **que nunca
  se asigna en ninguna línea del proyecto** (`grep` verificado). El TTS de la
  pregunta contextual y del refuerzo positivo suena siempre, incluso en modo
  privado (menor que C-10 porque es audio local, pero el candado era código
  muerto y sincronizarlo a mano era una trampa).
- **Corrección:** ambas líneas leen `self.cfg.modo_privado`, la misma fuente
  que C-10. Ya no existen tres banderas paralelas para la misma idea: solo
  `cfg.modo_privado`.

**C-12 · El botón `[ 🎤 Hablar ]` de la mascota ignoraba el modo privado** — *Alta (privacidad) — ✅ corregida*
- **Defecto:** `desktop_pet_native.py:185-191` llamaba
  `hablar_con_mascota_async(segundos=5.0)` sin ninguna información de
  privacidad: el flujo abría micrófono y enviaba a la nube aunque el agente
  estuviera en modo privado.
- **Corrección (doble capa):**
  1. **Consulta en vivo** (`desktop_pet_native.py:185-210`): el botón lee
     `GET http://127.0.0.1:<puerto>/api/estado` → campo `estado.modo_privado`
     (el engine lo escribe en `state.json`, `engine.py:1564`). Si está activo,
     muestra la burbuja *"🤫 Modo privado: sin voz por ahora"* y **no abre el
     micrófono**. Si el panel no responde, procede: el botón es una acción
     explícita del usuario y sin agente en marcha no hay sesión que proteger
     (la escucha automática queda blindada por C-10).
  2. **Defensa en profundidad** (`actions/groq_voice.py:467-486`):
     `hablar_con_mascota_async` acepta ahora `modo_privado: bool = False`; con
     `True` cancela **antes de abrir el micrófono** (0 audio capturado, 0
     tráfico) y avisa por burbuja vía `core.events`. El parámetro se propaga a
     `conversar_con_muse(..., modo_privado=...)`, que ya lo respetaba desde
     0.8.2 (`groq_voice.py:275-276`) y, con privado, nunca abre socket.

**C-13 · Modelo LLM inexistente pagaba un 404 en cada llamada** — *Media — ✅ corregida*
- **Defecto:** `MODELOS_LLM = ["qwen/qwen3.8-27b", "llama-3.3-70b-versatile",
  "llama-3.1-8b-instant"]`. El ID `"qwen/qwen3.8-27b"` no existe en el
  catálogo de Groq (los Qwen actuales son `qwen/qwen3-32b`); cada conversación
  o clasificación pagaba primero un HTTP 404 antes de caer al siguiente
  modelo: latencia extra en un flujo de voz (donde cada ms cuenta) y una
  línea de warning en cada turno.
- **Corrección** (`actions/groq_voice.py:26-29`): cadena real
  `llama-3.3-70b-versatile` → `llama-3.1-8b-instant`, con el mecanismo de
  fallback 404 conservado como resiliencia (no como camino normal).

**C-14 · 7 tests de regresión de privacidad** — *Añadido — ✅*
- **`tests/test_privacidad_voz.py`**: (1) N3 con modo privado no construye
  oyente ni abre micro; (2) N3 sin modo privado mantiene la escucha con sus
  opciones; (3) N3 sin clave Groq no intenta nube; (4) botón 🎤 con privado no
  llama a `grabar_audio` y avisa por burbuja; (5) botón 🎤 sin privado abre
  micro (flujo normal intacto); (6) `conversar_con_muse` con privado no abre
  socket; (7) **guarda estructural de fuente**: impide reintroducir los dos
  atributos fantasma del bug (`cfg.agente.modo_privado` en Notifier,
  `self.modo_privado` en engine). Suite: **256 passed, 0 failed**.

### Bloque C — hallazgos aceptados como pendientes (transparencia)

| ID | Hallazgo | Severidad | Estado |
|---|---|---|---|
| O-01 | `tts.py:84-87` desactiva la verificación SSL de edge-tts (`ssl._create_unverified_context()`) — vector MITM teórico | Media | **Pendiente**; recomendado: usar `certifi` / almacén del sistema y eliminar el parche |
| O-02 | `panel_static/pet-widget.html` hardcodea `null-wisp` como mascota por defecto y un `<select>` con nombres sin assets (solo `einstein` está en el paquete) | Media | **Pendiente**; el catálogo debe derivarse de `panel.py::pet_listar_disponibles` |
| O-03 | Ventana de micrófono fija en 5 s (botón) y 7 s (N3); el requisito original era 10–15 s y hoy no es configurable | Media | **Pendiente**; propuesta: sección `[voz]` con `segundos_escucha` |
| O-04 | `engine.py` acumula 1.683 líneas / 42 métodos (God-object en formación) | Media | En progreso: `CommandProcessor` ya se extrajo; quedan Pomodoro, fotos/cámara y refuerzo |
| O-05 | `chrome_extension/` ausente de este paquete sin mención documental | Baja | Verificar si fue deliberado |
| O-06 | Panel autentica por validación de Origin pero no por token; suficiente en `127.0.0.1`, opcional endurecer con token de arranque | Baja | Aceptado por diseño |
| O-07 | `datos/tts_cache/` (MP3 generados en runtime) sin poda de tamaño | Baja | Pendiente |
| O-08 | `run.py::cmd_auto` y `cmd_start` comparten helpers pero mantienen flujo duplicado | Baja | Parcial (C-09b) |

---

## 6. Roadmap de expansión: asistente TDAH multi-agente

Objetivo de la próxima fase: pasar de "mascota que vigila" a "asistente
personal proactivo por voz". Arquitectura prevista:

```text
        Voz del usuario ("Hey Einstein…") — botón 🎤 o Ctrl+Alt+M
                          │
        [ Router de intención · Groq llama-3.1-8b-instant ]
                          │
     ┌────────────────────┼─────────────────────┐
     ▼                    ▼                     ▼
 Agente Operativo    Agente Centinela        Agente Coach
 (acciones/tools)    (el engine actual)      (razonamiento profundo,
 - recordatorios      - deriva de foco        llama-3.3-70b-versatile)
 - brain dump Logseq  - pausa protegida      - priorización de semana
 - música de foco     - refuerzo positivo    - desglose en micro-pasos
```

Orden de implementación recomendado por el auditor:

1. **Brain dump con Logseq primero** (local-first, Markdown puro, ~1 día):
   *"Anota investigar el plugin de exportación"* → `- TODO …` en
   `journals/AAAA_MM_DD.md`. Máximo valor TDAH (libera memoria de trabajo),
   cero dependencias nuevas, cero nube.
2. **Rutinas sobre TOML** (`[rutinas]` en el config existente con recarga en
   caliente), evitando una dependencia YAML nueva.
3. **Vikunja después** (REST `POST /api/v1/tasks`), cuando haya valor
   demostrado en los recordatorios locales.
4. **Gate de privacidad antes de multiplicar agentes:** el router multi-agente
   amplía la superficie voz→nube; mantén todo bajo `cfg.modo_privado` (C-10 a
   C-12) y la futura sección `[voz]` opt-in.

---

## 7. Conclusión para el auditor

El paquete contiene una base estable, modular y con 256 pruebas automatizadas
verdes en dos plataformas. Las dos rondas de auditoría (A: seguridad web,
robustez y documentación; B: privacidad real de la voz) están aplicadas,
documentadas con archivo:línea y cubiertas por regresión automatizada. Los
hallazgos abiertos están declarados en el bloque C y priorizados; ninguno de
ellos afecta a la garantía central del producto: **con modo privado activado,
no hay capturas, no hay micrófono y no hay tráfico a la nube — ahora
verificado por tests.**
