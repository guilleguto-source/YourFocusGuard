# YourFocusGuard — Especificaciones y hoja de ruta para continuación

**Proyecto:** Asistente virtual de enfoque para TDAH (Windows, Python)
**Ubicación:** `C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard`
**Versión actual:** 0.8.2 (`yourfocusguard/__init__.py`)
**Estado:** Implementado y testeado (238 tests pasados, 2 saltados)
**Fecha:** 2026-11-09
**Propósito de este archivo:** Permitir que otro agente continúe el trabajo sin contexto previo.

---

## 1. Visión general

YourFocusGuard es un agente de productividad local para Windows que ayuda a mantener el foco en tareas de trabajo (ej. edición de fotos en Lightroom) sin capturas de pantalla indiscriminadas ni nube. Vigila qué app está al frente y la inactividad de teclado/ratón, y avisa al usuario si se desvía. Incluye:

- **Modo Sesión** (v0.2.0): declaras tarea + apps objetivo; R1 (fuera de app) y R2 (inactividad) disparan avisos graduales.
- **Modo Anclado** (v0.4.0): sin capturas, sin nube, solo predicados del SO.
- **Panel web local** (v0.3.0): `http://127.0.0.1:8756`, configuración en vivo, tema greige/beige + oscuro con Progressive Disclosure.
- **Mascota Flotante Nativa** (v0.8.2): Tkinter transparente con spritesheets, 59 mascotas, botón interactivo para hablar por voz y menú categorizado.
- **Voz Neuronal Muse y Diálogo Groq** (v0.8.2): Conversación empática por voz con Whisper y Groq LLM multimodelo, con atajo global `Ctrl+Alt+M`.
- **Modo Máxima Concentración** (v0.7.0): bloquea dominios en `hosts`, silencia audio, minimiza apps bloqueadas con red de seguridad.
- **Reconocimiento de Flujos de Trabajo** (v0.8.0): tolerancia contextual a herramientas auxiliares y aprendizaje activo.

---

## 2. Requisitos del usuario (resumidos de la conversación)

| # | Requisito | Estado |
|---|-----------|--------|
| 1 | Apps de trabajo: Lightroom, Lightroom Classic, Photoshop, Antigravity, Claude, Claude Code, DeepSeek, Harness, CapCut | ✅ En `user.toml` `[sesion] apps` |
| 2 | Tiempo inicial 90 min, configurable 30s–5min con barra deslizable | ✅ `segundos_fuera_app = 90`, `segundos_inactivo = 90`; sliders en panel |
| 3 | Estética greige/beige (nunca blanco), tema claro/oscuro | ✅ CSS ya implementado (`estilos.css`) |
| 4 | Prohibiciones: YouTube 1h (sin música), redes sociales | ✅ `[prohibiciones]` en `user.toml` |
| 5 | Asistente llama atención: solo / visual+sonido / traer Lightroom al frente tras 2.º-3.er llamado | ✅ `alertas.modo`, `traer_al_frente_app`, `traer_al_frente_tras` |
| 6 | Niveles de aviso 1, 2, 3, 5 apagables en settings | ✅ Interruptores en panel + `nivel_X_apagado` en config |
| 7 | OpenPets instalado y abierto | ⚠️ Usuario debe instalarlo; `proveedor = "auto"` lo detecta |
| 8 | Modo concentración con duraciones: 30min, 1h, 2h, 5h, hasta reinicio | ✅ Selector en panel + `duracion_min` |
| 9 | Cámara + MediaPipe (presencia/teléfono) — probar después | ✅ Implementado, `habilitada = false` por defecto |
| 10 | API tipo Groq para voz + micrófono 10-15s al preguntar | ❌ Pendiente (necesita API key de Groq) |
| 11 | Bloqueo YouTube: ¿desenfocada / cuadro negro? | ❌ Pendiente (actualmente bloquea a nivel hosts, navegador muestra error) |

---

## 3. Estructura del repositorio

```
YourFocusGuard/
├── run.py                          # CLI principal (start/panel/mascota/auto/session/doctor/...)
├── config/
│   ├── default.toml                # Valores de fábrica
│   ├── pc.toml                     # Perfil pc
│   ├── laptop.toml                 # Perfil laptop
│   └── user.toml                   # Ajustes del usuario (gitignored)
├── yourfocusguard/
│   ├── __init__.py                 # __version__ = "0.7.1"
│   ├── config.py                   # Carga TOML por capas + recarga en vivo
│   ├── engine.py                   # Motor: estados, Pomodoro, sesión, concentración, presencia
│   ├── session_guard.py            # Guardián de tarea: R1/R2 por predicados
│   ├── vigilante.py                # Prohibiciones: presupuestos diarios por primer plano
│   ├── mascota.py                  # Mascota tkinter integrada
│   ├── avatar/
│   │   ├── __init__.py
│   │   ├── base.py                 # Protocolo Avatar, mapeo estados→reacciones OpenPets
│   │   ├── factory.py              # crear_avatar(cfg): auto→openpets→tk→ninguno
│   │   ├── openpets.py             # Cliente IPC de OpenPets (pipe/TCP/unix)
│   │   └── focus_bridge.py         # Pet Assistant: start_session/pause/resume/status/concentracion/sigo
│   ├── panel.py                    # Panel web local (HTTP 127.0.0.1)
│   ├── panel_static/
│   │   ├── index.html              # SPA (tarjetas greige/beige)
│   │   ├── estilos.css             # Tema claro/oscuro, banda oscura prohibiciones
│   │   └── aplicacion.js           # Lógica vanilla JS
│   ├── capture/
│   │   ├── window_info.py          # Ventana activa, visibles multi-monitor, idle, escritorio bloqueado
│   │   ├── idle.py                 # GetLastInputInfo + GetTickCount (kernel32)
│   │   ├── screen.py               # Captura mss (solo si captura.habilitada=true)
│   │   ├── camera.py               # Webcam bajo demanda (OpenCV)
│   │   └── presencia.py            # MediaPipe rostro + manos (opt-in)
│   ├── actions/
│   │   ├── escalation.py           # Escalera N0-N3 (20/30/60/90s)
│   │   ├── concentr_acion.py       # Modo máxima concentración (hosts, audio, minimizar)
│   │   ├── notifier.py             # Consola + toast + voz
│   │   ├── tts.py                  # pyttsx3 en hilo propio con cola
│   │   ├── sound.py                # Beep suave N1
│   │   ├── toast.py                # winotify + fallback consola
│   │   └── window_actions.py       # traer_al_frente / minimizar_primera_plano (Win32)
│   ├── brain/
│   │   ├── base.py                 # Brain ABC + Verdict
│   │   ├── heuristic.py            # Nivel B local (app + título)
│   │   ├── gemini_brain.py         # Nivel A Gemini
│   │   ├── openai_brain.py         # Nivel A OpenAI
│   │   ├── router.py               # Router nube/local con disyuntor y caché
│   │   └── prompts.py              # SYSTEM_PROMPT_V1 + build_user_prompt
│   ├── privacy/
│   │   └── exclusions.py           # Ventanas excluidas (banca, contraseñas)
│   ├── memory/
│   │   ├── fifo.py                 # FrameBuffer de 5 frames en RAM
│   │   └── models.py               # FrameSnapshot
│   ├── storage/
│   │   └── db.py                   # SQLite (eventos, sesiones, presupuesto API, prohibiciones)
│   ├── console_ui.py               # Líneas de estado coloreadas
│   └── logging_setup.py            # Configuración de logs
├── tests/
│   ├── test_*.py                   # 25+ módulos de pruebas (pytest)
│   ├── conftest.py                 # Fixtures: cfg aislada en _pytmp/casos
│   └── __init__.py
├── requirements.txt                # Dependencias runtime
├── requirements-dev.txt            # pytest
├── README.md
├── CHANGELOG.md
└── data/                           # Creado al correr: db, logs, state.json, control.json, fotos/
```

---

## 4. Configuración actual (`config/user.toml`)

Este es el archivo que el usuario edita. Ya contiene sus apps y preferencias:

```toml
[sesion]
apps = ["lightroom", "lightroomclassic", "photoshop", "antigravity", "claude", "claude-code", "deepseek", "harness", "capcut"]
apps_auxiliares = ["explorer", "bridge"]
segundos_fuera_app = 90
segundos_inactivo = 90
exigir_primer_plano = true
monitor_objetivo = 0

[alertas]
modo = "completo"
traer_al_frente_app = "lightroom"
traer_al_frente_tras = 2
minutos_antes_de_traer = 2.0
nivel_1_apagado = false
nivel_2_apagado = false
nivel_3_apagado = false
nivel_5_apagado = false

[prohibiciones]
lista = [
  { patron = "youtube", limite_min_dia = 60, bloqueo_activo = true, excepciones = ["youtube music", "mix", "lofi"] },
  { patron = "instagram", limite_min_dia = 15, bloqueo_activo = true },
]

[concentracion]
habilitado = false
bloquear_hosts = true
silenciar_audio = true
dominios = ["youtube.com", "www.youtube.com", "instagram.com", "www.instagram.com", "tiktok.com", "www.tiktok.com"]
apps_bloqueadas = []
restaurar_al_salir = true
duracion_min = 0

[presencia]
habilitada = false
indice_camara = 0
intervalo_seg = 30
ausente_para_pausar_seg = 120

[avatar]
proveedor = "auto"
frases = true

[panel]
activo = true
puerto = 8756
abrir_navegador = true
```

**Importante:** Los tests usan una copia temporal de `config/` sin `user.toml` para no contaminar el archivo real del usuario.

---

## 5. Comandos CLI (`run.py`)

| Comando | Qué hace |
|---|---|
| `python run.py start` | Arranca agente + panel web + mascota |
| `python run.py panel` | Solo el panel web (sin agente) |
| `python run.py mascota --demo` | Prueba la mascota integrada |
| `python run.py auto "tarea" [--detectar 20] [--concentracion]` | **Todo-en-uno**: detecta apps, inicia sesión, activa concentración, arranca agente |
| `python run.py session start "tarea" --apps a,b --detectar 20` | Declara sesión de trabajo |
| `python run.py session status` | Estado de la sesión activa |
| `python run.py session stop` | Cierra sesión con resumen |
| `python run.py pause [min]` | Pausa rápida |
| `python run.py resume` | Reanuda |
| `python run.py sigo` | "Sigo en la tarea" (cierra aviso) |
| `python run.py stop` | Detiene el agente |
| `python run.py status` | Estado actual y resumen del día |
| `python run.py test-alert [n]` | Prueba niveles 1..n de la escalera |
| `python run.py doctor` | Diagnóstico de instalación |
| `python run.py inspect [seg]` | Muestra ventana activa cada N s (para armar listas) |

Atajos globales (Windows): `Ctrl+Alt+F12` pausa/reanuda, `Ctrl+Alt+F11` sigo, `Ctrl+Alt+F10` pausa corta.

---

## 6. Cómo poner en marcha otro agente

### Paso 1: Entorno

```bat
cd "C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard"
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Paso 2: Verificar

```bat
python run.py doctor
python -m pytest tests/ -q   # debe dar 224 passed, 2 skipped
```

### Paso 3: Arrancar

```bat
python run.py start
```

Luego abrir `http://127.0.0.1:8756` en el navegador.

---

## 7. Pendientes / próximos pasos (Fase 3 y más)

### Inmediato (bajo esfuerzo)

1. **API Groq para voz + micrófono**: El usuario quiere que el asistente responda con voz vía Groq y active el micrófono 10-15s cuando pregunte. Requiere:
   - API key de Groq en `.env`
   - Nueva integución en `actions/tts.py` o nuevo módulo `actions/groq_voice.py`
   - Activar micrófono por ventana limitada cuando el motor dispara `_pregunta_contextual`

2. **Bloqueo YouTube visual**: Actualmente bloquea a nivel `hosts` (el navegador muestra error de DNS). El usuario preguntó si se puede mostrar sección desenfocada o cuadro negro. Esto requeriría una extensión de navegador o inyección CSS, fuera del alcance actual de Python puro.

### Medio plazo

3. **MediaPipe presencia**: `presencia.habilitada = true` en `user.toml` + instalar `opencv-python-headless` y `mediapipe`. Probar en Windows real.
4. **Instalador / autoarranque**: Empequetar con PyInstaller y agregar al inicio de Windows.
5. **OpenPets real**: El protocolo IPC está implementado y testeado con simulador TCP, pero no validado contra OpenPets instalado (falta red para descargarlo desde el entorno del agente).

### Largo plazo

6. **SmolVLM/Moondream en CPU** (Nivel C) para análisis local sin nube.
7. **Reporte semanal y calibración de umbrales**.

---

## 8. Limitaciones conocidas

- **OpenPets**: no instalado en el entorno del agente; no se pudo validar el named pipe real. El código de `avatar/openpets.py` y `avatar/focus_bridge.py` está probado con un servidor TCP simulado.
- **PyPI**: no accesible desde el entorno del agente; `pip install -r requirements.txt` debe ejecutarse localmente por el usuario.
- **Cámara/MediaPipe**: requiere `opencv-python-headless` y `mediapipe` (no en `requirements.txt` por defecto).
- **Voz Groq**: no implementada; actualmente usa pyttsx3 (voz de Windows).
- **Privilegio de administrador**: el modo concentración que edita `C:\Windows\System32\drivers\etc\hosts` necesita ejecutarse como administrador. Sin él, avisa y sigue con las otras medidas.
- **Tests de pytest cache**: puede quedar `pytest-cache-files-*` en la carpeta; están gitignored.

---

## 9. Decisiones de diseño clave (no tocar sin motivo)

- **Capturas de pantalla desactivadas por defecto** (`captura.habilitada = false`): el usuario pidió privacidad. El agente vive por predicados del SO.
- **Configuración en español**: las claves TOML están en español porque las edita el usuario.
- **Tests aislados**: `conftest.py` copia `config/` a `_pytmp/casos/` y no lee `user.toml` real. No modificar esta invariante.
- **state.json**: escrito cada ciclo; el panel lo lee para mostrar estado en vivo.
- **control.json**: archivo de control para comandos externos (pause, resume, session_start, etc.).

---

## 10. Contacto / contexto para el siguiente agente

Si necesitas más contexto, revisa:
- `CHANGELOG.md` para el historial de cambios por versión
- `README.md` para la documentación de usuario completa
- `docs/fase-1-2-como-probar.md` y `docs/fase-0-como-probar.md` para guías de prueba
- Los tests en `tests/` son la mejor documentación de comportamiento esperado

**Última versión estable:** 0.7.1 — todo implementado y verde.
