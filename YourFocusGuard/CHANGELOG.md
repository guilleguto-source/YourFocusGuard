# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · versionado [SemVer](https://semver.org/lang/es/).

## [0.8.3] — 2026-11-10

**Corrección de privacidad real del modo privado en los tres caminos de voz.**
En 0.8.2 el candado existía pero leía atributos equivocados y nunca cerraba:
con `modo_privado = true` el agente seguía abriendo el micrófono y enviando
audio/texto a Groq. Ahora la escucha automática, el botón 🎤 de la mascota y el
TTS de pregunta/refuerzo leen todos la bandera real `cfg.modo_privado`, con
7 tests de regresión nuevos que lo garantizan.

### Corregido

- **`actions/notifier.py` (escucha automática tras aviso N3)**: el candado leía
  `cfg.agente.modo_privado`, un atributo que **no existe** en `AgenteCfg`
  (solo tiene `perfil`, `maquina`, `prompt_id`) y `getattr` devolvía siempre
  `False`. Ahora lee `cfg.modo_privado`, la bandera de nivel superior que
  escriben `load_config`/`--privado` y `CommandProcessor` (`core/commands.py`,
  comando `privado`). Con modo privado: TTS local sí suena, pero **no se abre
  el micrófono y no se publica nada a Groq**.
- **`engine.py:1459` y `engine.py:1490` (pregunta contextual y refuerzo
  positivo)**: leían `getattr(self, "modo_privado", False)`, un atributo del
  engine **que nunca se asignaba** (candado muerto). Ahora leen
  `self.cfg.modo_privado`.
- **`desktop_pet_native.py` (botón `[ 🎤 Hablar ]`)**: llamaba a
  `hablar_con_mascota_async()` sin información de privacidad. Ahora consulta
  el estado en vivo del agente (`GET /api/estado` del panel local, campo
  `estado.modo_privado`) y, si el modo privado está activo, muestra la burbuja
  "🤫 Modo privado: sin voz por ahora" y no abre el micrófono. Si el panel no
  responde procede (el botón es una acción explícita del usuario y sin agente
  en marcha no hay sesión que proteger); la escucha automática sigue blindada
  por el motor.
- **`actions/groq_voice.py::hablar_con_mascota_async`**: acepta el nuevo
  parámetro `modo_privado`; con `True` cancela el flujo antes de abrir el
  micrófono (0 audio capturado, 0 red) y avisa por burbuja. Defensa en
  profundidad: el parámetro se propaga también a `conversar_con_muse`, que ya
  lo respetaba desde 0.8.2.
- **`actions/groq_voice.py::MODELOS_LLM`**: se retiró el ID inexistente
  `"qwen/qwen3.8-27b"`. Cada conversación pagaba primero un HTTP 404 antes de
  caer al siguiente modelo de la cadena (latencia extra + ruido de log).
  La cadena queda: `llama-3.3-70b-versatile` → `llama-3.1-8b-instant`.

### Añadido

- **`tests/test_privacidad_voz.py`** (7 tests): (1) N3 con modo privado no
  construye oyente ni abre micro; (2) N3 sin modo privado mantiene la escucha
  automática con sus opciones; (3) N3 sin clave Groq no intenta nube; (4) el
  botón 🎤 con modo privado no llama a `grabar_audio` y avisa por burbuja;
  (5) el botón 🎤 sin modo privado abre micro (flujo normal); (6)
  `conversar_con_muse` con privado no abre socket (defensa en profundidad);
  (7) guarda estructural de fuente: nadie puede volver a leer
  `cfg.agente.modo_privado` ni `self.modo_privado` (los dos atributos
  fantasma del bug original). Suite total: **256 pasados**.

## [0.8.2] — 2026-11-08

### Añadido
- **Mascota Flotante Nativa para Windows (`desktop_pet_native.py`)**: Mascota transparente con Tkinter nativo y `-transparentcolor`, interactiva con arrastre, píldora `[ 🎤 Hablar ]` y submenú contextual.
- **Catálogo de 59 Mascotas**: Normalización y aplanado de los 59 spritesheets de OpenPets con categorización alfabética ergonómica.
- **Voz Neuronal estilo Muse y Groq Whisper**: edge-tts + Groq LLM multimodelo con personalidad empática y atajo global `Ctrl+Alt+M`.
- **Progressive Disclosure en Panel Web**: Secciones inactivas colapsadas visualmente para reducir sobrecarga cognitiva en TDAH.
- **Seguridad Web y Robustez**: Protección contra Path Traversal, validación de Origin contra CSRF, delimitadores en `hosts` y cierre limpio de hilos de audio.

## [0.8.0] — 2026-11-07

### Añadido
- **Reconocimiento de Flujos de Trabajo (`workflow_groups.py`)**: Tolerancia contextual a herramientas auxiliares vinculadas (Lightroom + Gutoflow / Bridge) antes de disparar alertas.
- **Modo Aprendizaje Activo**: Preguntas amables para descubrir nuevas aplicaciones de trabajo.

## [0.7.0] — 2026-11-06

**Fase 3**: el asistente deja de solo avisar y empieza a actuar —
modo máxima concentración, detección de presencia física, y el Pet
Assistant de OpenPets habla con tu agente por el mismo IPC.

### Añadido — Fase 3: modo máxima concentración

- **`yourfocusguard/actions/concentracion.py`**: `ModoConcentracion` ejecuta
  medidas reales cuando activas una sesión de máxima concentración:
  - Bloquea dominios distractores (YouTube, Instagram, TikTok, Netflix…) en
    el archivo hosts de Windows (`127.0.0.1` por dominio), con `ipconfig /flushdns`.
  - Silencia el audio del sistema (mute del dispositivo de salida por defecto
    vía `waveOutSetVolume`).
  - Minimiza procesos bloqueados cada vez que vuelven al primer plano.
  - Todo se deshace al cerrar la sesión o al desactivar el modo (`restaurar_al_salir`).
- **Nueva sección `[concentracion]`** en la configuración: `habilitado`,
  `bloquear_hosts`, `silenciar_audio`, `dominios`, `apps_bloqueadas`,
  `restaurar_al_salir`.
- Se integra en `state.json` (bloque `concentracion`: activo, dominios,
  duración) y en el panel (sección "Modo Máxima Concentración").
- Nunca lanza: si no hay privilegios para editar el hosts o no se puede
  silenciar el audio, el agente avisa y sigue con las otras medidas.

### Añadido — Fase 3: detección de presencia física

- **`yourfocusguard/capture/presencia.py`**: `DetectorPresencia` usa
  MediaPipe (FaceDetection + Hands) bajo demanda: abre la cámara, toma
  UN frame, evalúa si hay rostro (¿estás en la silla?) y si hay manos
  (¿teléfono en la mano?), y suelta la cámara. Opt-in: solo cada
  `intervalo_seg` y nunca de forma continua.
- **Nueva sección `[presencia]`**: `habilitada`, `indice_camara`,
  `intervalo_seg`, `ausente_para_pausar_seg`, `telefono_en_mano_seg`.
- En el Modo Sesión, si no se detecta rostro durante
  `ausente_para_pausar_seg`, el guardián se **pausa solo** sin avisar.
- Graceful degradation total: sin `opencv-python-headless` o sin
  `mediapipe`, devuelve "no disponible" y el agente sigue igual.
- Se integra en `state.json` (bloque `presencia`) y en el panel.

### Añadido — Fase 3: Pet Assistant de OpenPets

- **`yourfocusguard/avatar/focus_bridge.py`**: `FocusBridge` expone, sobre
  el mismo IPC de OpenPets que ya usa el avatar (`hello` / `pet.react` /
  `pet.say`), las capacidades del Pet Assistant:
  - `focus.start_session`: inicia una sesión con tarea, apps y duración.
  - `focus.pause` / `focus.resume`: pausa y reanuda el agente.
  - `focus.status`: devuelve estado actual, tarea, apps y si hay sesión.
  - `focus.concentracion`: activa/desactiva el modo máxima concentración.
  - `focus.sigo`: responde "sigo en la tarea" (cierra el aviso).
- Las respuestas van como burbuja de OpenPets (`pet.say`) para que el
  usuario las vea en su mascota sin salir del flujo.
- El puente se inicia al arrancar el agente y se para al apagarlo; si
  OpenPets no está abierto, el puente no se activa y el agente funciona
  igual.

### Añadido — Todo automático

- **`python run.py auto "tarea" [--detectar 20] [--concentracion]`**:
  detecta las apps que estás usando, declara la sesión, opcionalmente activa
  el modo máxima concentración y arranca el agente con panel web — todo en
  un solo comando.

### Cambiado

- Versión `0.6.0` → `0.7.0` (`yourfocusguard/__init__.py`).
- `config.py`: secciones `[concentracion]` y `[presencia]` registradas en
  `_SECCIONES` y `_SECCIONES_RECARGABLES` (recarga en vivo desde el panel).
- `engine.py`: inyección de `concentracion`, `presencia` y `focus_bridge`;
  comprobación de concentración en cada ciclo (minimizar apps bloqueadas);
  comprobación de presencia en `_tick_sesion` (auto-pausa si no hay rostro);
  estado en `state.json` para ambos.
- `run.py`: `cmd_start` inyecta los tres nuevos componentes al `Agent`;
  nuevo comando `auto`.
- `panel.py` + SPA (`index.html`, `aplicacion.js`): controles de
  concentración (dominios, apps, hosts, audio) y presencia (intervalo,
  umbral de ausencia, índice de cámara, teléfono), y estado en la tarjeta
  del avatar.
- 25 tests nuevos: `test_concentracion.py`, `test_presencia.py`,
  `test_focus_bridge.py`. Suite total: **224 pasados, 2 saltados**.

## [0.6.0] — 2026-11-06

**Fases 1 y 2**: la sesión se declara desde el panel (y se puede detectar) y el
asistente puede poner la cara de **OpenPets** sin dejar de usar la mascota
integrada cuando OpenPets no está abierto.

### Añadido — Fase 1: sesión declarable y en caliente

- **Anclas editables en vivo**: `GuardianSesion.reconfigurar()` recompila los
  patrones cuando cambia `[sesion] apps`; el agente lo aplica en el siguiente
  sondeo sin reiniciar. Una sesión declarada a mano (`session start --apps`)
  manda sobre el TOML y no se pisa por debajo.
- **Panel > "Sesión de hoy"**: tarea, programas de trabajo y toleradas;
  botones **Iniciar sesión**, **Cerrar sesión** y **Detectar apps (10 s)**.
  Los programas se guardan como predeterminados en `user.toml`.
- **`POST /api/detectar`** y `python run.py session start "..." --detectar 20`:
  muestrean el primer plano y proponen las apps que de verdad usas, filtrando
  las neutras (explorador, terminal…).
- **`sesion.monitor_objetivo`** (0 = cualquiera): además de estar al frente, la
  ventana debe estar en ese monitor — "trabajo siempre en el segundo".

### Añadido — Fase 2: avatar OpenPets

- **`yourfocusguard/avatar/`**: interfaz común (`Avatar`), fábrica y cliente
  del **IPC local de OpenPets** (named pipe o TCP, token de descubrimiento en
  `%APPDATA%\OpenPets\runtime\ipc.json`, JSON de una línea, timeouts propios).
  Métodos usados: `hello`, `pet.react`, `pet.say`.
- **`[avatar] proveedor = auto | openpets | tk | ninguno`**: `auto` intenta
  OpenPets y cae a la mascota tkinter si no responde. El motor no cambia una
  sola regla: habla con la misma interfaz.
- **Mapeo de estados**: FOCO→`working`, ESCALADA→`error`, PAUSA→`waiting`,
  EN_ESPERA→`idle`; los avisos van como burbuja (`pet.say`) con frase de una
  línea acotada a 140 caracteres.
- **Degradación real**: los envíos van por cola y hilo propios (un OpenPets
  colgado no bloquea la vigilancia); tras 3 fallos seguidos, 60 s de silencio
  y relectura del descubrimiento.
- El panel muestra qué cara está activa ("OpenPets" / "mascota integrada").

### Limitación conocida

- Con OpenPets la pregunta contextual va como burbuja **sin botones** (el IPC
  público no expone entrada de usuario); se responde con `Ctrl+Alt+F11/F10` o
  `run.py sigo`. Los botones siguen disponibles en la mascota tkinter, y el
  chat/voz llegará con el Pet Assistant en la Fase 3.

## [0.5.0] — 2026-11-06

**Fase 0** de la revisión: el agente deja de reclamarte cuando no estás y pasa a
escucharte cuando te reclama. Sin cambios en la configuración existente: todo
lo nuevo tiene valores por defecto conservadores.

### Corregido

- **Pantalla bloqueada, suspensión o idas largas**: antes R2 seguía contando y
  te avisaba con el equipo bloqueado; al volver del almuerzo se disparaba la
  escalera completa de golpe (toast + voz + "traer al frente"). Ahora
  `sesion.ausencia_seg` (300 s por defecto) detecta bloqueo de sesión
  (`OpenInputDesktop`), suspensión y idle largo, y **pausa el guardián sin
  avisar**; al volver se reanuda limpio.
- **Fotos de webcam en Windows**: el motivo `disparo:inactivo_en_app` lleva dos
  puntos, ilegal en un nombre de archivo; el guardado fallaba con WinError 87 y
  la foto se perdía en silencio. Ahora el nombre se sanea.
- **Los tests contaminaban la configuración real**: el fixture `cfg` leía y
  escribía el `config/` del proyecto, así que correr `pytest` podía cambiar tu
  `user.toml` (de hecho activaba la captura de pantalla). Ahora se copia a una
  carpeta temporal y no se lee el `user.toml` personal.
- **El TTS bloqueaba el bucle**: `runAndWait()` congelaba la vigilancia 3-6 s.
  La voz corre ahora en un hilo con cola acotada.

### Añadido

- **Canal de respuesta** a la pregunta contextual. El avatar muestra una
  ventana con botones ("Sigo aquí", "Pausa 10 min", "Estoy leyendo") y hay
  atajos globales: `Ctrl+Alt+F11` = sigo, `Ctrl+Alt+F10` = pausa corta
  (`privacidad.pausa_corta_min`). También `python run.py sigo`.
- **"Estoy leyendo"** da 5 minutos de gracia al reloj de inactividad sin
  cerrar la regla de "fuera de la app".
- **`sesion.exigir_primer_plano`** (false por defecto): con `true`, una app
  visible en el otro monitor **no** cuenta como presente — es la petición
  literal "quiero que Lightroom esté al frente".
- **`alertas.minutos_antes_de_traer`** (2 min por defecto): el "traer al
  frente" ya no salta a los 30 s; exige que el desvío lleve su tiempo y que
  haya **dos llamados con peso** (toast/voz), no el aviso sutil.
- Frase del asistente al traerte de vuelta: "Es momento de seguir trabajando".

### Cambiado

- La **pregunta contextual cubre N0 y N1**: ya no vuelven a sonar a los 20 y
  30 segundos del mismo episodio (eran cinco estímulos en 90 s).
- `escritorio_bloqueado()` nuevo en `capture/window_info.py` (una llamada
  barata por sondeo, sin tocar teclado ni pantalla).

## [0.4.0] — 2026-11-07

Reorientación pedida por el usuario: **la cámara y la captura de pantalla
pasan a un segundo plano (opcionales)**; el agente se guía por lo que hace
la computadora (qué app está al frente y la inactividad).

### Cambiado

- **Capturas de pantalla fuera del mapa**: nueva clave `captura.habilitada`
  (false por defecto). Con `false`, el agente arranca en **Modo Anclado**:
  usa el guardián de tarea por predicados (primer plano + idle, R1/R2) sin
  capturas, sin FIFO, sin nube; si lo detienen por panel/CLI se re-activa
  solo en el siguiente ciclo. Las apps ancla vienen de `[sesion].apps`
  (o por CLI `session start`); sin apps ancla funciona como vigilante
  genérico de inactividad.
- **`sesion.capturar_al_disparar` ahora es false por defecto**: al disparar
  una regla ya no se toma captura de pantalla de evidencia.
- El slider "Desvío sostenido" del Panel queda como ajuste del modo
  monitoreo; los tiempos del Modo Anclado siguen siendo R1/R2 (30 s - 5 min).

### Añadido

- **Pregunta contextual al disparar una regla** (petición del usuario):
  al abrir un episodio el asistente pregunta con contexto — si la webcam
  está habilitada toma UNA foto para entender qué pasa ("te tomé una foto
  para entender qué está pasando…") y si no, pregunta directo: "¿Qué estás
  haciendo en este momento? ¿Necesitas hacer una pausa?". Respeta los
  canales de `alertas.modo` y queda registrada como `pregunta_contextual`.
- **Excepciones en prohibiciones** (`ProhibicionCfg.excepciones`): "YouTube
  prohibido pero la música permitida" — `excepciones = ["youtube music",
  "mix", "lofi"]` hace que esos títulos no cuenten para el presupuesto ni
  disparen el bloqueo. Máximo 8 por entrada; también editables desde el
  Panel (campo "Permitido (excepciones)" y chip "YouTube · 60 min (sin
  música)").

## [0.3.0] — 2026-11-07

Panel del Guardián + agente mascota + prohibiciones: la configuración visual
que pidió la usuaria ("un lugar para configurar la frecuencia del monitoreo...
que permita configurar diversas cosas"), y el agente puesto a funcionar en
pantalla antes de pasar a la cámara.

### Añadido

- **Panel del Guardián** (`panel.py` + `panel_static/`, http://127.0.0.1:8756,
  solo localhost): página de ajustes con la estética pedida — **claro
  greige/beige (nunca blanco) y banda oscura** para las prohibiciones, con
  tema claro/oscuro conmutable. Sin dependencias nuevas (http.server):
  - **Frecuencia de monitoreo** (slider 5-60 s) con derivados al estilo de la
    imagen de referencia: capturas/hora, ventana FIFO y RAM estimada.
  - **Pantalla principal**: selector de monitor para la captura (con dos
    monitores, `listar_monitores()` vía EnumDisplayMonitors +
    GetMonitorInfoW). La detección de primer plano/inactividad sigue siendo
    global: una app visible en el otro monitor cuenta como presente.
  - **Tiempos de intervención** (sliders 30 s - 5 min): desvío sostenido del
    modo monitoreo y reglas R1/R2 de la sesión.
  - **Modo de aviso**: solo visual / visual + sonido / **completo** (tras el
    2.º o 3.er llamado, la app de trabajo **vuelve al frente**).
  - Botones de pausar/reanudar/detener/**probar avisos** (por control.json,
    como la consola) y estado en vivo (5 s).
  - Guarda en `config/user.toml` (escritor TOML propio, stdlib) y el agente
    **recarga en vivo** al ciclo siguiente (`Config.refrescar_si_cambia`:
    muta las secciones en el mismo objeto, así escalera, guardián y vigilante
    ven los cambios sin reiniciar).
- **Prohibiciones con presupuesto diario** (`vigilante.py` + migración 002:
  tabla `presupuesto` fecha+patrón): "no permitir YouTube 1 hora, o redes
  sociales". Cuenta el **primer plano** por proceso o título (regex simple),
  sin capturas; sobrevive reinicios y caduca al día siguiente. Al agotarse:
  toast una vez y, con **bloqueo activo**, la app se minimiza cada vez que
  vuelve al frente hasta mañana (y si el modo es completo, tu app de trabajo
  vuelve al frente). Máximo 12 patrones; en ventanas excluidas no se cuenta
  nada. `run.py status` muestra el consumo del día.
- **Agente mascota** (`mascota.py`, tkinter + temas, sin dependencias nuevas):
  siempre visible, arrastrable, clic → abre el panel. Estados dormida/atenta/
  **alerta (rebota)**/pausa (con taza)/descanso, avisos como burbuja de texto.
  **Apariencia cambiable**: temas clasico (greige) / oscuro / calido, o el
  tuyo en `TEMAS`; se degrada sola sin escritorio (SSH/servidor). vPet puede
  coexistir como decoración, pero no es controlable desde el agente.
- **Medidas sobre ventanas** (`actions/window_actions.py`, Win32 puro):
  `traer_al_frente` (AttachThreadInput + SW_RESTORE si estaba minimizada) y
  `minimizar_primera_plano` (bloqueo activo). Fuera de Windows degradan a
  None/False.
- **Modos de aviso en la escalera**: `alertas.modo` filtra canales — "visual"
  silencia N1 (beep) y N3 (voz); la mascota (N0) y el toast (N2) son visuales.
- **CLI**: `panel` (solo panel, `--puerto`/`--sin-abrir`), `mascota`
  (`--demo`, `--tema`), `start --sin-panel`; `test_alert` también por
  control.json (botón del panel).
- **Config**: secciones `[prohibiciones]`, `[mascota]`, `[panel]`; claves
  `alertas.modo/traer_al_frente_app/traer_al_frente_tras`; `state.json`
  incluye `presupuestos` y `avisos`.
- 37 tests nuevos (panel HTTP con puerto efímero, vigilante con DB real,
  window_actions puro, mascota headless, motor v0.3.0): total **154**.

### Privacidad

- El panel escucha **solo en 127.0.0.1** (nunca la red) y no pide credenciales
  de API: solo lee `state.json`/SQLite y escribe `user.toml`/`control.json`.
- Las prohibiciones miran únicamente el par (proceso, título) de la ventana
  activa — cero capturas — y en ventanas excluidas no se cuenta nada.

## [0.2.1] — 2026-11-07

Verificación con webcam bajo demanda: la pieza que faltaba de la propuesta
del usuario ("si pasan más de 20 segundos sin tocar el mouse ni el teclado,
que solo entonces haga una foto con la cámara para verificar").

### Añadido

- **Regla R0 · verificación suave** (`engine.py`): con una sesión activa, si
  la app objetivo está presente (al frente, visible en otro monitor o
  auxiliar tolerada) y el input lleva `verificar_con_camara_seg` (20 s por
  defecto) sin moverse, se toma **UNA foto de webcam** por episodio de
  inactividad. Silenciosa: no abre episodio, no toca la escalera, no envía
  nada a la nube. Se rearma sola cuando vuelve el input.
- **Foto al disparar**: cuando una regla R1/R2 abre el episodio y la webcam
  está habilitada, además de la captura de pantalla se toma UNA foto de
  constancia (`camara:disparo:<motivo>` en la base).
- **`capture/camera.py` real** (antes era la reserva de la F3): con OpenCV
  (`opencv-python-headless`) abre la webcam, toma `preframes` frames de
  estabilización, captura UNO, reescala a `ancho_max` (640 px), comprime a
  JPEG y cierra. La lámpara de la cámara se enciende 1-2 s por foto; nunca
  queda encendida de forma continua. Import perezoso: sin OpenCV degrada a
  None y el guardián sigue funcionando por predicados.
- **Sección `[camara]`** en la configuración: `habilitada` (**false** por
  defecto: opt-in), `indice`, `ancho_max`, `calidad_jpeg`, `preframes`,
  `foto_en_disparo`, `guardar_fotos` (false = la foto vive solo en RAM),
  `retencion_dias` (poda de `data/fotos/AAAA-MM-DD/`, 7 días).
- **Guardar y podar fotos**: `data/fotos/<día>/<hora>_<motivo>.jpg` con
  escritura atómica y poda por día al arrancar cada sesión.
- **CLI**: `python run.py test-cam` toma una foto de prueba y muestra la
  ruta (la forma rápida de verificar índice, encuadre y lámpara); `doctor`
  ahora chequea la webcam (aviso, no crítico) y `session start` anuncia el
  umbral de verificación si la cámara está activa.
- Registro en SQLite de cada foto (`tipo=deteccion`, `accion=foto`,
  motivo `camara:<motivo>:<kb>kb` o `camara:<motivo>:falla`) y en
  `state.json` (`sesion.fotos`, `sesion.camara`, `sesion.verificado_idle`).
- Resumen de cierre de sesión: menciona cuántas fotos de verificación se
  tomaron.
- 18 tests nuevos (módulo con cv2 falso + integración del motor): total
  **117**.

### Privacidad

- La cámara es **opt-in** y solo dispara por eventos: 20 s de congelamiento
  en una sesión, o una regla R1/R2. Jamás en ventanas excluidas ni en modo
  privado (mismos candados que la captura de pantalla).
- Sin OpenCV instalado el agente funciona igual; solo falta la foto.

## [0.2.0] — 2026-11-07

Modo Sesión: guardián de tarea por predicados, sin capturas indiscriminadas
(propuesta del usuario durante la retrospectiva del sprint 1).

### Añadido

- **Modo Sesión** (`session_guard.py`): declaras "tengo que terminar esta
  sesión de fotos" y el agente deja de capturar pantallas; pasa a vigilar
  dos predicados baratos del SO cada 5 s:
  - **R1 · fuera_de_app**: ninguna app objetivo en primer plano NI visible
    en ningún monitor durante `segundos_fuera_app` (60 s).
  - **R2 · inactivo_en_app**: sin tocar ratón ni teclado durante
    `segundos_inactivo` (60 s; configurable hasta los 20 s originales).
  - Cero capturas, cero nube y cero coste mientras se cumplen las reglas;
    al disparar, UNA captura de evidencia y la escalera gradual existente
    (aviso → toast → voz) con enfriamiento y tope horario compartidos.
- **Multi-monitor real**: `capture/window_info.ventanas_visibles()` enumera
  ventanas visibles en todos los monitores (EnumWindows + IsWindowVisible +
  IsIconic + WS_EX_TOOLWINDOW + DWMWA_CLOAKED, monitor por
  MonitorFromWindow). Con Lightroom visible en el segundo monitor y una
  referencia al frente, la sesión sigue "en app".
- Apps objetivo y auxiliares con regex simple (`light.?room` cubre Lightroom
  Classic); apps auxiliares (explorer, Bridge...) no cuentan como ausencia;
  ventanas excluidas por privacidad no disparan ni capturan evidencia.
- Backdating honesto del episodio: t0 = momento en que se rompió la regla,
  no cuando se detectó; los minutos de los avisos son los reales.
- CLI: `session start "texto" --apps a,b --aux c --min N`, `session stop`,
  `session status`; confirmación por toast y resumen de cierre (minutos en
  tarea, alertas) por toast y en SQLite.
- `state.json` incluye bloque `sesion` (apps, último visto, idle, fin
  programado, disparos) para que `status` y otras consolas lo lean.
- Sección `[sesion]` en la configuración (default + laptop + user.toml.example)
  con validación de umbrales.
- Pausas manuales/Pomodoro durante la sesión: silencian al guardián y al
  reanudar resetean su reloj de ausencia (el café no cuenta como desvío).
- 19 tests nuevos (guardián puro + integración): total **99**.

### Cambiado

- El bucle del agente usa `intervalo_sondeo` (5 s) con sesión activa en vez
  de `captura.intervalo_seg` (15 s): sondeo más fino y sin imágenes.
- `MOTIVO_TEXTO` de la escalera extendido con los motivos de sesión.

## [0.1.0] — 2026-11-07

Primer sprint: fases F0-F2 de la hoja de ruta del blueprint (MVP funcional).

### Añadido

- **F0 — Fundaciones**: estructura del paquete, configuración TOML por capas
  (default → perfil pc/laptop → user), captura de pantalla con mss + metadatos
  (app activa, título, idle, pantalla completa vía ctypes, sin pywin32),
  SQLite de eventos con el esquema del Apéndice B, consola de debug.
- **F1 — Bucle con cerebro**: FIFO de 5 frames en RAM, Nivel A conmutable
  (Gemini `google-genai` / OpenAI `gpt-4o-mini`) con prompt v1, salida JSON
  estricta y reintento único; Nivel B heurístico local (app + título + idle,
  estilo ActivityWatch); router con cadencia de análisis, caché por ventana,
  disyuntor de fallos y presupuesto diario con corte automático; veredictos
  débiles (< 0.6) que no mueven el estado.
- **F2 — Intervención**: máquina de estados (EN_ESPERA/FOCO/PAUSA/ESCALADA/
  COOLDOWN) con histéresis de 2 ciclos limpios; escalera de alertas
  t+20/30/60/90 (mascota→consola, aviso, toast winotify, voz pyttsx3);
  enfriamiento de 5 min y tope de 4 escaladas/hora; orquestador Pomodoro
  25/5 con pausa larga; reglas anti-falso-positivo (transiciones breves,
  pantalla completa silenciosa, exclusiones, idle > 2 min); pausa manual por
  CLI, archivo de control y atajo global Ctrl+Alt+F12; modo privado.
- CLI completa: `start pause resume stop status task inspect test-alert
  doctor export purge`.
- 80 tests de lógica pura (reloj y capturadores falsos; sin Windows ni claves).
- Migración 001 de esquema: columnas `accion_sugerida` y `origen` en `evento`
  + tabla `consumo_api` (trazabilidad de calibración F5 y presupuesto).

### Pendiente (siguientes sprints)

- F3: webcam (MediaPipe, celular/conversación/mirada).
- F4: mascota PyQt6 con 6 estados, bandeja, Nivel C en CPU, PyInstaller.
- F5: reporte semanal y calibración de umbrales.
