# Revisión de YourFocusGuard v0.4.0 + plan para integrar OpenPets / VPet

**Fecha:** 2026-11-06 · **Revisado:** `C:\Users\Guill\Downloads\YourFocusGuard_v0.4.0\YourFocusGuard\`
**Referencias:** [LorisYounger/VPet](https://github.com/LorisYounger/VPet) · [OpenPetsHQ/openpets](https://github.com/OpenPetsHQ/openpets)

> **Estado (2026-11-06): Fases 0, 1 y 2 aplicadas.** El código vive en
> `ADHD Assistant/YourFocusGuard/` como **v0.6.0**: sesión declarable desde el
> panel con detección de apps y anclas en caliente (F1), y avatar OpenPets por
> IPC local con degradación a la mascota tkinter (F2). Pendiente: Fase 3
> (plugin puente + voz/chat del Pet Assistant, concentración real y MediaPipe).
> Los dos bugs que la suite no podía ver —`GetTickCount` en user32 y los dos
> puntos en el nombre de la foto— quedaron corregidos y con test de regresión.


---

## 1. Resumen ejecutivo

El proyecto ya implementa **casi toda la lógica de vigilancia** que pediste: primer plano,
inactividad, dos monitores, ventana por encima de las demás, cámara bajo demanda y
prohibiciones con presupuesto. El problema no es que falte motor: es que **el motor está
bien y la experiencia alrededor está incompleta**:

1. **Tu `config/user.toml` está encendiendo el modo contrario al que quieres.**
   `[captura] habilitada = true` vuelve al pipeline de capturas de pantalla + análisis en
   la nube cada 60 s y **desactiva el Modo Anclado** (v0.4.0), que es exactamente el que
   vigila "Lightroom al frente / sin tocar nada".
2. **No hay forma de declarar la sesión desde el asistente.** Las apps ancla solo se
   declaran por consola (`session start --apps ...`) y el panel web no expone ese campo.
3. **El asistente pregunta y no puede escuchar la respuesta.** `_pregunta_contextual`
   pregunta "¿necesitas una pausa?" pero no hay botones, ni atajo, ni chat.
4. **Faltan tres guardas anti-falso-positivo** que en tu caso se van a notar mucho:
   pantalla bloqueada, suspensión/ausencia larga y "estoy leyendo, no me molestes".
5. **La escalera dispara demasiado rápido y en ráfaga.** Al abrir el episodio ya hay
   pregunta contextual y, en 90 s, cuatro avisos más; y el "traer al frente" llega a los
   ~30 s, no tras dos llamados "de verdad".

Sobre los dos proyectos: **OpenPets es el compañero correcto para este asistente** y se
puede integrar **sin escribir TypeScript**, porque publica un protocolo IPC local
documentado (pipe con token) al que Python puede hablar directamente. **VPet no tiene ese
canal**: para "combinarlo" habría que escribir un plugin en C#/.NET 8 y arrastrar un
segundo toolchain. La recomendación es **OpenPets como cara, Python como cerebro, y VPet
solo como decoración opcional** (o no usarlo).

---

## 2. Qué entendí que quieres (especificación funcional)

Lo escribo como criterios verificables, porque es lo que voy a usar para decir "esto está
hecho" o "esto falta":

| # | Comportamiento pedido | Criterio de aceptación |
|---|---|---|
| R1 | Al empezar, el asistente sabe **qué tarea** y **con qué programas** | Puedo decirlo hablando o escribiendo; queda registrado y visible |
| R2 | Si salgo de Lightroom **más de 1 min** → me llama la atención | Aviso con nombre de la app y tono no punitivo |
| R3 | Si estoy en Lightroom pero **sin tocar teclado/mouse > 1 min** → me llama | Distingue "fuera de app" de "congelado en app" |
| R4 | Tras **2 llamados** sin volver → **pone Lightroom al frente** y me lo dice | Solo tras 2 avisos reales, no a los 30 s |
| R5 | **Modo máxima concentración** a pedido: sin YouTube, sin redes | Bloqueo desde el minuto 0 mientras esté activo |
| R6 | **Cámara opt-in**: si no reacciono ~2 min, foto de constancia | 1 foto por episodio, guardada con fecha/motivo |
| R7 | Si no estoy en la silla → **pregunta o se pausa solo** | No me regaña por haberme ido al baño |
| R8 | Todo debe funcionar con **dos monitores** | Sabe en qué monitor está la app y si está al frente |
| R9 | El asistente **habla** y tiene presencia visual ("mascota") | Reacciona al estado, dice frases con contexto |
| R10 | Que la app **se vea bonita / con más opciones** | Se puede cambiar de mascota sin tocar el motor |

Tus requisitos R2/R3 los cumples con `[sesion] segundos_fuera_app = 60` y
`segundos_inactivo = 60`. R4, R7 y R10 son donde está el trabajo real.

---

## 3. Mapa: lo que pediste → dónde está hoy

Leyenda: ✅ hecho · ⚠️ parcial · ❌ falta

| Requisito | Implementación actual | Estado |
|---|---|---|
| R1 tarea + apps | `session start "texto" --apps a,b` (`run.py:270`), `[sesion] apps` (`config.py:199`), `_iniciar_sesion` (`engine.py:724`) | ⚠️ solo consola; ni el panel ni el asistente lo preguntan |
| R2 fuera de app | R1 de `GuardianSesion` (`session_guard.py:181-186`), umbral `segundos_fuera_app` | ✅ |
| R3 inactivo en app | R2 (`session_guard.py:191-193`), `GetLastInputInfo` (`capture/idle.py:25`) | ✅ |
| R4 traer al frente | `_quizas_traer_al_frente` (`engine.py:411`), `traer_al_frente` (`actions/window_actions.py:125`), `traer_al_frente_tras=2` | ⚠️ dispara a los ~30 s (cuenta N0+N1); solo en `modo = "completo"` |
| R4bis decir "es momento de seguir" | no existe; el aviso es genérico (`escalation.py:180-210`) | ⚠️ |
| R5 máxima concentración | presupuestos diarios + minimizar (`vigilante.py:127-168`), `bloqueo_activo` | ⚠️ no es on-demand ni desde 0 min; minimizar no silencia audio |
| R6 foto si no reacciono | R0 a los 20 s (`engine.py:534-551`), `verificar_con_camara_seg=20`, foto al disparo (`engine.py:628`) | ⚠️ 20 s, no 2 min; la foto no se analiza |
| R7 no estoy en la silla | — | ❌ solo hay inactividad; no hay detección de presencia (MediaPipe es F3) |
| R8 dos monitores | `ventanas_visibles` / `apps_visibles` (`window_info.py:134-214`), monitor por ventana | ⚠️ demasiado permisivo: si Lightroom está visible en el otro monitor **no cuenta como ausencia** |
| R9 voz + presencia | `mascota.py` (tkinter), `actions/tts.py`, `actions/toast.py` | ✅ base, pero sin diálogo |
| R10 cambiar de mascota sin tocar el motor | `TEMAS` en `mascota.py:36` | ⚠️ 3 temas dibujados a mano; no hay avatares externos |

---

## 4. Hallazgos de código (priorizados)

### P0 — rompen la experiencia tal como la describiste

**P0-1 · `user.toml` activa el modo equivocado.**
`config/user.toml:16` tiene `[captura] habilitada = true`. Eso enciende el pipeline
clásico (captura cada 15 s, FIFO, nube cada 60 s) y **anula el Modo Anclado**
(`engine.py:277`: el modo anclado solo se activa si `captura.habilitada` es `false`).
Además, sin `[sesion] apps` declaradas, el modo clásico **no vigila "Lightroom al frente"**:
solo clasifica apps contra `heuristica.apps_enfoque`, y `lightroom` no está en esa lista
(`config/default.toml:40-45`).
*Arreglo inmediato:* `habilitada = false` (o activar el modo anclado con apps declaradas).

**P0-2 · No hay exención de pantalla bloqueada / suspensión / ausencia larga.**
En modo sesión, `_tick_sesion` (`engine.py:511`) no consulta
`heuristica.idle_ausencia_seg` (eso solo pasa en el pipeline clásico, `engine.py:314-319`).
Si bloqueas Windows o cierras el portátil:
- R2 sigue evaluando y a los 60 s abres episodio (y con cámara, intenta una selfie);
- al volver del almuerzo, `off_since` se retrocede (`engine.py:555`) y, en un solo tick,
  `ladder.tick` dispara N0+N1+N2+N3 → toast + voz + "traer al frente" de golpe
  (`escalation.py:128-149`).

*Arreglo:* detectar `idle > umbral_ausencia` (p. ej. 10 min) o sesión bloqueada
(`OpenInputDesktop` / `WTSQuerySessionInformation`) → **pausa automática** del episodio y
reanudar limpio al volver. Y tope de tiempo transcurrido entre ticks (como el `DELTAPE_SEG=90`
que ya usa `vigilante.py:33`).

**P0-3 · Pregunta sin canal de respuesta.**
`_pregunta_contextual` (`engine.py:462-505`) dice "¿Necesitas hacer una pausa?" y no hay
manera de contestar: el toast (`actions/toast.py:21`) no tiene botones, no hay atajo, no hay
chat. Para TDAH esto es peor que no preguntar.
*Arreglo:* (a) atajos globales — `Ctrl+Alt+F12` ya pausa/reanuda (`engine.py:942`), añadir
`Ctrl+Alt+F11` = "sigo en la tarea" y `Ctrl+Alt+F10` = "pausa 10 min"; (b) botones en el
toast — winotify soporta hasta 5 acciones y callbacks; (c) cuando OpenPets esté integrado,
la pregunta va al chat/voz del Pet Assistant.

**P0-4 · Ráfaga de avisos al abrir episodio.**
Al disparar R1/R2 se ejecutan: pregunta contextual (inmediata) + N0 mascota (t+20) + N1
(t+30) + N2 toast (t+60) + N3 voz (t+90). Cinco estímulos en 90 s.
*Arreglo:* la pregunta contextual **reemplaza** a N0/N1 del episodio (marcar
`ladder._disparadas` o abrir la escalera en t+20), y subir el espaciado.

**P0-5 · El "traer al frente" no respeta "dos llamados".**
`_llamados_episodio` se incrementa con **cualquier** alerta (`engine.py:875`), incluidas N0
(consola) y N1 (beep) → con `traer_al_frente_tras = 2` la ventana salta a los **~30 s**.
*Arreglo:* contar solo avisos con peso (N2/N3) o añadir
`alertas.minutos_antes_de_traer = 3`; y decir la frase "es momento de seguir trabajando"
*después* de traerla, no antes.

### P1 — calidad y robustez

**P1-1 · El TTS bloquea el bucle.** `tts.speak` usa `runAndWait()` (`actions/tts.py:46`):
3-6 s en los que el agente **no mide nada**; con sondeo de 5 s, te pierdes un tick entero.
*Arreglo:* hilo dedicado con cola (como ya hace `Mascota` con su `queue.Queue`).

**P1-2 · Las anclas no se pueden cambiar en caliente.** `guardia.iniciar` compila los
patrones una vez (`session_guard.py:126`); `refrescar_si_cambia` muta `cfg.sesion` pero no
recompila. El panel además **no expone apps**: `construir_overlay` solo acepta
`segundos_fuera_app` e `segundos_inactivo` (`panel.py:190-202`).
*Arreglo:* `GuardianSesion.reconfigurar(apps)` que recompile si cambia la firma, y un campo
"apps de la sesión" en el panel/CLI de arranque.

**P1-3 · "Bloquear" no bloquea.** `minimizar_primera_plano` (`window_actions.py:170`)
minimiza la ventana en primer plano: si YouTube está en una pestaña de Chrome, **se
minimiza todo Chrome** (pierdes las demás pestañas) y **el audio sigue sonando**.
*Opciones reales:* silenciar la sesión de audio del proceso (pycaw), cerrar la pestaña por
título (frágil), o bloqueo de dominio por hosts/DNS o extensión de navegador (efectivo,
requiere admin). Recomiendo: **mute + minimizar** para el modo suave y **hosts** para
"máxima concentración".

**P1-4 · Multi-monitor demasiado permisivo.** `_presencia` (`engine.py:598-612`) devuelve
`VISIBLE` si la app está en cualquier monitor, y `VISIBLE` cuenta como "presente". Tú
pediste "Lightroom **al frente**". Debe ser configurable:
`sesion.exigir_primer_plano = true|false` y, opcional, `sesion.monitor_objetivo = 1|2`.

**P1-5 · `apps_enfoque` no incluye Lightroom.** En modo clásico, Lightroom es
"desconocida" (`brain/heuristic.py:86-102`): no molesta, pero tampoco confirma foco (y el
prompt de la nube no sabe que es tu trabajo del día).

**P1-6 · Tope de escalada silencioso.** `ladder.begin` puede devolver `False` por
`tope_por_hora` y `_tick_sesion` ignora el retorno (`engine.py:560`): el estado queda en
ESCALADA pero no llega ningún aviso.

**P1-7 · Ruido de fondo.** En modo anclado se escribe `state.json` y una línea de consola
cada 5 s (`engine.py:585-590`, `1123`). No rompe nada, pero desgasta SSD y ensucia la
consola.

### P2 — menores / deuda

- `_vigilar` corre antes de las pausas: el presupuesto se consume en pausa (deliberado,
  documentado, pero conviene decidirlo con el usuario).
- `_iniciar_sesion` no cierra un episodio abierto si arrancas sesión en modo clásico.
- Las fotos se guardan 7 días (`config.py:188`) y **nadie las mira**: el valor está en la
  constancia, pero se podría añadir un visor/resumen semanal.
- `panel.activo`/`puerto` están en `_SECCIONES_RECARGABLES` (`config.py:504`) pero el
  servidor no se reinicia al cambiarlos: recarga fantasma.
- El README promete "154 tests"; conviene ejecutarlos en el equipo del usuario antes de
  tocar nada (`python -m pytest tests/ -q`).

---

## 5. Lo que yo cambiaría hoy (30 minutos, sin tocar código)

```toml
# config/user.toml
[captura]
habilitada = false            # ← Modo Anclado: sin capturas, sin nube

[sesion]
apps = ["lightroom", "lightroomclassic", "photoshop"]  # tus anclas
apps_auxiliares = ["explorer", "bridge", "chrome"]      # toleradas al consultar refs
segundos_fuera_app = 60
segundos_inactivo = 60
verificar_con_camara_seg = 120   # tu idea: foto a los 2 min, no a los 20 s

[alertas]
modo = "completo"
traer_al_frente_app = "lightroom"
traer_al_frente_tras = 3      # mientras se corrige el contador

[prohibiciones]
lista = [
  { patron = "youtube", limite_min_dia = 60, bloqueo_activo = true,
    excepciones = ["youtube music", "mix", "lofi"] },
]
```

Y para arrancar en modo sesión desde consola, mientras no exista el flujo conversacional:

```bat
python run.py session start "editar fotos de la boda" --apps lightroom,lightroomclassic,photoshop --aux explorer,bridge
```

---

## 6. VPet vs OpenPets (con datos, no impresiones)

| | **VPet** | **OpenPets** |
|---|---|---|
| Stack | C# / WPF (.NET 8, `net8.0-windows`) | Electron + TypeScript |
| Licencia | Apache-2.0 (animaciones del core con **atribución obligatoria**; uso comercial requiere aviso/contacto) | MIT |
| Cómo se extiende | **Plugin C#**: NuGet `VPet-Simulator.Windows.Interface`, Visual Studio/.NET 8 SDK, DLL en la carpeta de mods | **Plugin TS/JS** (SDK v3, sandbox, permisos) **o IPC local** |
| API para procesos externos | **No hay** (solo plugins .NET dentro de la app) | **Sí**: IPC JSON por líneas sobre named pipe + token (documentado) |
| Voz / conversación | Plugin ChatGPT + EdgeTTS de la comunidad | **Pet Assistant nativo**: chat + TTS + STT, usa tus claves |
| Look | 384 animaciones, Workshop, mods de la comunidad | Sprites animados, galería de mascotas, temas |
| Plataforma | Windows | Windows/macOS/Linux |
| Coste de integrarlo con tu agente Python | **Alto**: proyecto C#, segunda app, segundo runtime | **Bajo/medio**: cliente IPC en ~80 líneas de Python; plugin solo si quieres capacidades en el chat |

### Por qué OpenPets y no VPet (por ahora)

OpenPets ya es, conceptualmente, lo que tú quieres: un **compañero de escritorio con
plugins y capa de agente**. Su documentación de [IPC](https://github.com/OpenPetsHQ/openpets/blob/main/docs/ipc.md)
describe exactamente lo que necesitas:

- Discovery: `%APPDATA%\OpenPets\runtime\ipc.json` con `endpoint` y `token`.
- Endpoint Windows: `\\.\pipe\openpets-<hex>-<pid>`.
- Mensajes: **una línea JSON** `{id, version:1, token, method, params}`; respuesta
  `{ok:true,result}` o `{ok:false,error:{code,message}}`; timeouts 2 s / 3 s; 16 KB máx.
- Métodos: `hello`, `status`, `pets.list`, `pet.react`, `pet.say`, `pet.showMedia`,
  `lease.acquire|heartbeat|release`.
- Reacciones (enum cerrado): `idle, thinking, working, editing, running, testing, waiting,
  waving, success, error, celebrating`.
- `pet.say` valida el texto: **una línea, corta, sin URLs/rutas/secretos**.

Eso te da, gratis, la **cara y la voz**. Y su [SDK v3](https://github.com/OpenPetsHQ/openpets/blob/main/docs/sdk.md)
tiene `ctx.net` con permiso `network:local` para que un plugin declare y llame a tu API
local `127.0.0.1`, y `ctx.assistant.registerCapability(...)` para que el **asistente del
chat** pueda invocar acciones (p. ej. "empecemos sesión de fotos") sin que tú escribas el
diálogo.

VPet no tiene nada de eso: sería un front-end muy bonito, aislado, que hay que conectar con
un plugin en C#. Si te gusta el personaje, la ruta sensata es **dejarlo como decoración**
(no reacciona al estado) y no intentar fusionar los dos proyectos: sus formatos, licencias
y runtimes son incompatibles.

---

## 7. Arquitectura propuesta: cerebro en Python, cara intercambiable

```
┌──────────────────────────── Python · yfg-core ────────────────────────────┐
│  sensors (Win32)                 motor                    acciones         │
│  ├ primer plano/título           ├ episodios + anclas      ├ toasts+botones │
│  ├ idle de entrada               ├ escalera gradual        ├ atajos globales│
│  ├ ventanas visibles/monitores   ├ prohibiciones           ├ traer al frente│
│  └ webcam bajo demanda           └ Pomodoro/pausas         └ mute/minimizar │
│                                                                           │
│  API local 127.0.0.1:8757 (token)   ◄── panel web                         │
│  avatar (interfaz)  ──► openpets_ipc.py │ tk_mascota.py │ null.py         │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ named pipe + token (JSON por líneas)
                            ┌───────▼────────┐
                            │   OpenPets     │  mascota visible + voz
                            │  (Electron)    │  Pet Assistant (chat/TTS/STT)
                            └───────▲────────┘
                                    │ (opcional) plugin "Focus Bridge"
                                    │ ctx.net → 127.0.0.1:8757
                                    └ capacidades: focus.start_session, focus.pause, focus.status
```

### 7.1 Contrato del avatar (refactor pequeño y clave)

Hoy el motor habla con `Mascota` en ~10 sitios (`engine.py:136-137, 242, 384, 437, 492,
892, 1050, 1181`). Se sustituye por una interfaz:

```python
class Avatar(Protocol):
    def iniciar(self) -> None: ...
    def estado(self, estado: str, detalle: str = "") -> None: ...
    def decir(self, texto: str) -> None: ...
    def reaccionar(self, nivel: int, texto: str) -> None: ...
    def preguntar(self, texto: str, opciones: list[tuple[str, str]]) -> None: ...
    def parar(self) -> None: ...
```

Implementaciones reales (v0.6.0): `avatar/openpets.py` (IPC) y la mascota
tkinter existente, elegidas por `avatar/factory.py` según `[avatar] proveedor`
(`auto` cae a tkinter). No hizo falta un `null.py`: "sin cara" es `None`.
El motor no sabe qué hay detrás; mañana puede ser VPet sin tocar reglas.

### 7.2 Cliente IPC de OpenPets en Python (boceto)

```python
import json, os, win32file, win32pipe   # pywin32 ya viene con pyttsx3

def _discovery() -> dict:
    ruta = os.path.join(os.environ["APPDATA"], "OpenPets", "runtime", "ipc.json")
    with open(ruta, encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["protocol"] == "openpets-ipc" and d["protocolVersion"] == 1
    return d

def enviar(method: str, params: dict | None = None) -> dict:
    d = _discovery()
    h = win32file.CreateFile(d["endpoint"], win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                             0, None, win32file.OPEN_EXISTING, 0, None)
    try:
        req = {"id": os.urandom(6).hex(), "version": 1, "token": d["token"],
               "method": method, "params": params or {}}
        win32file.WriteFile(h, (json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            _, trozo = win32file.ReadFile(h, 65536)
            buf += trozo
        return json.loads(buf)
    finally:
        h.Close()

# estado FOCO -> ("working", "en Lightroom · editar boda")
# estado ESCALADA -> ("error", "¿qué pasó? ¿volvemos?")
# pausa -> ("idle", ...)
```

Mapeo sugerido: `EN_ESPERA→idle`, `FOCO→working` (o `editing` si la app es Lightroom/Photoshop),
`ESCALADA→error`, `COOLDOWN→thinking`, `PAUSA→idle`, y `waving` justo después de traerte la
app al frente.

### 7.3 El flujo conversacional (lo que hoy no existe)

Con OpenPets, el diálogo sale del **Pet Assistant**, no de tu código:

1. Al arrancar, el asistente (voz/chat) pregunta: "¿Qué toca hoy? ¿Fotos o código?".
2. El modelo llama a la capacidad `focus.start_session` (registrada por el plugin puente),
   que hace `POST http://127.0.0.1:8757/session` con `{tarea, apps}`.
3. Tu motor arranca anclas, y el avatar reacciona a los estados.
4. Si detectas desvío, `pet.say` con una frase corta y, si hace falta, `ctx.ui.alert`.
5. Al cerrar: `focus.stop_session` devuelve el resumen (minutos en tarea, avisos, fotos) y
   el asistente lo cuenta.

**Sin OpenPets** (si no quieres instalarlo todavía), el 80 % del valor se consigue con:
toasts con botones (winotify `add_actions`), tres atajos globales y una pregunta al arrancar
por consola (`input()` con timeout).

### 7.4 Detección automática de anclas (tu idea de "que vea qué abro")

`python run.py session start "editar fotos" --detectar 90`: muestrea el primer plano cada
2 s durante 90 s, ordena por tiempo y propone `apps = [...]` (con confirmación). Es barato
(usa lo que ya existe: `get_active_window`) y elimina el tener que saberse los nombres de
proceso.

---

## 8. Plan por fases

### Fase 0 · Correcciones P0 (1-2 días) — ✅ aplicada en v0.5.0
- [x] Exención de pantalla bloqueada + suspensión + ausencia larga (pausa automática).
- [x] Canal de respuesta: atajos `Ctrl+Alt+F11` / `Ctrl+Alt+F10` y botones en la mascota.
- [x] Reordenar la escalera: la pregunta contextual sustituye a N0/N1; el "traer al frente"
      cuenta solo avisos de peso + `minutos_antes_de_traer`.
- [x] `user.toml` correcto y `apps_enfoque += lightroom` (queda como Fase 1 si se usa el modo clásico).
- [x] Extras encontrados al probar en Windows real: `GetTickCount` estaba en user32
      (R2 mudo) y el nombre de las fotos llevaba `:` (no se guardaban).
- [x] Los tests ya no tocan `config/user.toml` real.
- **Hecho =** con la pantalla bloqueada 10 min no llega ni un aviso; al volver, uno solo.

### Fase 1 · Sesión declarable y en caliente (2-3 días) — ✅ aplicada en v0.6.0
- [x] `GuardianSesion.reconfigurar()` + recarga en vivo de `[sesion] apps`.
- [x] Campo de tarea/apps y botones de sesión en el panel (y `--detectar` en la CLI).
- [x] `sesion.exigir_primer_plano` (v0.5.0) y `monitor_objetivo`.
- **Hecho =** cambio de anclas sin reiniciar; el panel arranca la sesión con Lightroom.

### Fase 2 · Cara OpenPets (3-4 días) — ✅ aplicada en v0.6.0
- [x] Interfaz `Avatar` + `avatar/openpets.py` (cliente IPC + cola + degradación).
- [x] Mapeo de estados/reacciones y frases cortas validadas.
- [x] Fallback automático a la mascota tkinter si OpenPets no está abierto.
- **Hecho =** con OpenPets abierto, la mascota reacciona y habla; sin OpenPets, todo sigue.
- **Nota**: la pregunta con botones no existe por IPC; se responde con atajos. El
  chat/voz del Pet Assistant queda para la Fase 3 (plugin puente).

### Fase 3 · Diálogo y concentración (1 semana)
- [ ] API local `127.0.0.1:8757` con token + plugin "Focus Bridge" (SDK v3).
- [ ] Capacidades `focus.start_session / pause / status` para el Pet Assistant.
- [ ] Modo máxima concentración on-demand (preset: límite 0 + mute + hosts opcional).
- [ ] Frase post-traer-al-frente: "es momento de seguir trabajando".

### Fase 4 · Presencia (opcional, después)
- [ ] MediaPipe: celular en mano / no hay nadie en la silla / mirada fuera.
- [ ] Pausa automática por ausencia y reanudación al volver.

---

## 9. Riesgos y decisiones abiertas

1. **Privacidad**: la cámara y las fotos en disco son lo más delicado; hoy son opt-in y
   con retención de 7 días (`config.py:181-188`). Si añadimos análisis de fotos, decidir si
   se envía a la nube o se queda en local (OpenPets permite Ollama / LM Studio).
2. **Doble app**: OpenPets añade ~200 MB y un proceso Electron. Alternativa: seguir con
   tkinter y solo añadir toasts con botones.
3. **Bloqueo real de sitios**: hosts/DNS requiere admin y afecta a todo el equipo; la
   extensión de navegador es lo más limpio, pero es otro proyecto.
4. **Licencia de animaciones de VPet**: si algún día se usa para algo comercial, hay
   obligación de atribución y aviso; OpenPets es MIT sin esas ataduras.
5. **Windows-only**: todas las piezas nuevas (Win32, toasts, atajos) son Windows; el motor
   de reglas sigue siendo puro y testeable.

---

## 10. Anexo · Mapeo de reacciones OpenPets

| Estado del motor | Reacción | Frase de ejemplo |
|---|---|---|
| EN_ESPERA | `idle` | "listo cuando tú" |
| FOCO | `working` / `editing` | "en Lightroom, bien" |
| sospecha (< 30 s) | `thinking` | "¿sigues ahí?" |
| ESCALADA | `error` | "¿nos distrajimos?" |
| PAUSA | `waiting`/`idle` | "pausa, sin culpa" |
| tras traer al frente | `waving` | "es momento de seguir trabajando" |
| cierre de sesión | `success` / `celebrating` | "2 h en la tarea, 3 avisos" |
| error de cámara/permiso | `error` | "no pude abrir la cámara" |
