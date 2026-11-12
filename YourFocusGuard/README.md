# YourFocusGuard

Agente visual de productividad para la gestión de la atención con TDAH en Windows.
Observa tu pantalla, evalúa si mantienes la continuidad de la tarea y te devuelve
al foco con una escalera de avisos gradual y **no punitiva**: nunca bloquea apps
ni te grita; primero pone cara rara, luego susurra, y solo si hace falta te habla.

> **Aviso honesto**: YourFocusGuard es una herramienta de apoyo a la autorregulación,
> no un dispositivo médico ni un sustituto del tratamiento. Si los avisos te estresan
> más de lo que ayudan, bájale los umbrales o apágalo: está diseñado para servirte.

Este repositorio implementa las fases **F0 → F2** de la hoja de ruta del blueprint
(fundaciones, bucle con nube e intervención), el **Modo Sesión** (v0.2.0:
guardián de tarea por predicados, sin capturas), la **verificación con webcam
bajo demanda** (v0.2.1), el **Panel del Guardián + agente mascota** (v0.3.0),
el **Modo Anclado** (v0.4.0: capturas de pantalla fuera del mapa y cámara
opcional; el agente se guía por el primer plano y la inactividad), la
**Fase 0 de la revisión** (v0.5.0: ausencia real, canal de respuesta de la
pregunta y escalera contenida), las **fases 1 y 2** (v0.6.0: sesión
declarable desde el panel con detección de apps y **avatar OpenPets** como
cara opcional) y la **Fase 3** (v0.7.0: **modo máxima concentración**,
**detección de presencia física** y **Pet Assistant de OpenPets**). El resto
de la F3 (MediaPipe: celular, conversación, mirada) llega en los siguientes
sprints.

---

## Cómo funciona (en 30 segundos)

**Modo Anclado (v0.4.0, el modo por defecto)** — el que pidió el usuario:

```
el primer plano manda (0 imágenes, 0 nube, 0 API):
    ¿saliste de tu app de trabajo (Lightroom, tu editor...) > 1 min?  ->  te llama
    ¿estás en la app pero sin tocar ratón ni teclado > 1 min?         ->  te llama
    ¿te fuiste (pantalla bloqueada, suspensión, idle > 5 min)?        ->  se pausa solo
al llamar te pregunta con contexto:
    con webcam (opt-in): UNA foto para entender qué pasa  ("¿qué está pasando? ¿pausa?")
    sin webcam: pregunta directo                          ("¿qué estás haciendo? ¿pausa?")
    y puedes responder: botones en la mascota, Ctrl+Alt+F11 (sigo) o Ctrl+Alt+F10 (pausa)
prohibiciones: YouTube con música permitida (excepciones), redes sociales, etc.
```

**Modo monitoreo clásico (opt-in con `captura.habilitada = true`)**:

```
captura (mss, 15 s)  ->  FIFO 5 frames en RAM (45-75 s)  ->  cerebro
                                                        ├─ Nivel A: Gemini / GPT-4o-mini (visión)
                                                        └─ Nivel B: heurística local (app + título + idle)
->  máquina de estados (FOCO / ESCALADA / COOLDOWN / PAUSA)
->  escalera: t+20 s gesto · t+30 s aviso · t+60 s toast · t+90 s voz
->  SQLite local (decisiones, nunca imágenes)
```

**Modo Sesión (v0.2.0 + cámara v0.2.1)** — alternativa sin imágenes para trabajo declarado:

```
declaras: "session start editar fotos --apps photoshop,lightroom"
sondeo de predicados cada 5 s (cero capturas, cero nube, cero API):
    R0  ¿en la app pero N s sin tocar ratón ni teclado?  -> UNA foto de webcam (verificación)
    R1  ¿ninguna app de la sesión al frente NI visible en ningún monitor?  > 60 s  ->  escala
    R2  ¿app presente pero sin tocar ratón ni teclado?                     > 60 s  ->  escala
solo al disparar: UNA captura de evidencia (+ foto de webcam si la cámara está activa)
```

Windows sabe en todo momento qué ventana está en primer plano (una por sistema)
y qué ventanas son visibles en cada monitor (EnumWindows). Con dos monitores,
Lightroom puede estar abierto en el segundo mientras consultas una referencia:
el Modo Sesión lo cuenta como "presente" y no te molesta. Solo cuando la regla
se rompe de verdad se toma la evidencia y arranca la escalera gradual.

**Panel + prohibiciones + mascota (v0.3.0)** — todo lo demás se ajusta sin tocar
archivos:

```
http://127.0.0.1:8756  (solo tu equipo, nunca la red)
    frecuencia de captura · pantalla a capturar (2 monitores)
    tiempos de intervención (30 s - 5 min, sliders)
    avisos: solo visual / visual+sonido / completo (trae tu app al frente)
    prohibiciones: "no permitir YouTube más de 1 h" con barra de progreso
    mascota: temas clasico / oscuro / calido
```

Tres principios del blueprint que se respetan a rajatabla:

1. **La memoria antes que el juicio**: un frame aislado nunca es una distracción;
   solo el desvío sostenido 30 s o más dispara la escalera.
2. **Escalada suave**: la primera alerta es casi invisible y la última sigue siendo amable.
3. **Privacidad por construcción**: las capturas del pipeline viven solo en RAM
   (máx. 75 s) y nunca tocan el disco; las ventanas excluidas (banca, contraseñas)
   ni se capturan. Única excepción, opt-in: las fotos de verificación de la webcam
   (v0.2.1), guardadas solo si tú activas la cámara.

## Requisitos

- Windows 10/11 (el desarrollo se probó en Linux a nivel lógico: 199 tests)
- Python **3.11** o superior — descárgalo de [python.org](https://www.python.org/downloads/)
  y marca "Add Python to PATH" al instalar
- Opcional: una clave de API para el Nivel A
  ([Gemini, gratis de prueba](https://aistudio.google.com/apikey) o
  [OpenAI](https://platform.openai.com/api-keys)). Sin clave funciona igual
  con la heurística local.
- Opcional: [OpenPets](https://github.com/OpenPetsHQ/openpets/releases)
  instalado y abierto si quieres que la cara del asistente sea su mascota
  animada (`[avatar] proveedor = "auto"`).

## Instalación (Windows, 5 minutos)

Abre PowerShell o CMD en la carpeta del proyecto:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edita `.env` y pega tu clave (`GEMINI_API_KEY=...` o `OPENAI_API_KEY=...`).
Luego verifica que todo esté listo:

```bat
python run.py doctor
```

## Uso diario

En una consola (déjala abierta):

```bat
python run.py start
```

Con el arranque se abre el **Panel del Guardián** en tu navegador
(`http://127.0.0.1:8756`) y aparece la **mascota** en la esquina del escritorio.
¿No quieres panel ni mascota? `python run.py start --sin-panel` y
`[mascota] visible = false`.

Verás una línea por captura: hora, estado coloreado, app activa, quién opinó
(nube o heurística) y con cuánta confianza. Ejemplo:

```
14:32:05  FOCO       pycharm           Blueprint — capítulo 3            heuristica 0.75
14:35:20  FOCO       chrome            Docs tesis                        nube:gemini 0.92
  >> señal de desvío: video (0.85, heuristica)
14:36:35  ESCALADA   chrome            YouTube - gatitos                 heuristica 0.85
    ¿Seguimos con la tarea? Llevas 1 min en vídeo o streaming.
```

En **otra consola** (funcionan a la vez; se comunican por archivo de control):

| Comando | Qué hace |
|---|---|
| `python run.py start` | arranca el agente **con panel web y mascota** (Ctrl+C detiene todo) |
| `python run.py panel` | solo el Panel del Guardián (sin agente), para configurar a gusto |
| `python run.py mascota --demo` | la guardiana en pantalla ciclando sus estados (pruébala) |
| `python run.py pause` | pausa 15 min (`pause 30` para media hora) |
| `python run.py resume` | reanuda antes de tiempo |
| `python run.py sigo` | **v0.5.0**: "sigo en la tarea" — cierra el aviso actual sin pausar |
| `python run.py stop` | cierra el agente limpiamente |
| `python run.py status` | estado actual + resumen del día + últimos eventos |
| `python run.py task "Escribir tesis cap 3"` | declara tu tarea (mejora los avisos y el prompt) |
| `python run.py session start "Editar fotos boda" --apps photoshop,lightroom` | **Modo Sesión**: guardián de tarea sin capturas (ver abajo) |
| `python run.py session start "Editar fotos" --detectar 20` | **v0.6.0**: detecta solo las apps que estás usando y declara la sesión |
| `python run.py session status` | cómo va la sesión activa (última vez en app, input, alertas) |
| `python run.py session stop` | cierra la sesión con resumen (minutos en tarea, alertas) |
| `python run.py inspect` | muestra tu ventana activa cada 2 s: úsalo para armar tus listas |
| `python run.py test-alert` | dispara los 3 niveles de la escalera para probar toast y voz |
| `python run.py test-cam` | toma UNA foto con la webcam y te muestra dónde quedó (si activaste `[camara]`) |
| `python run.py export` | exporta los eventos de la semana a CSV (Excel-friendly) |
| `python run.py purge --si` | borra todos los eventos registrados |
| `python run.py auto "editar fotos" [--detectar 20] [--concentracion]` | **v0.7.0**: todo-en-uno — detecta apps, declara la sesión, activa concentración y arranca el agente |

También hay **atajos globales** (solo Windows; si no funcionan, usa la CLI):
`Ctrl+Alt+F12` pausa/reanuda, `Ctrl+Alt+F11` = "sigo en la tarea" (cierra el
aviso) y `Ctrl+Alt+F10` = pausa corta (`privacidad.pausa_corta_min`, 10 min).

### Modo Sesión: guardián de tarea (v0.2.0)

Para trabajo que TÚ declaras, la vigilancia no necesita imágenes. Dices
"ahora voy a editar fotos" y el agente vigila dos predicados baratos del
sistema operativo (ventana al frente / visible, e idle de entrada):

```bat
python run.py session start "editar fotos de la boda" --apps photoshop,lightroom,lightzone --aux explorer --min 180
```

- **R1 · fuera de la app**: con `exigir_primer_plano = false`, ninguna app
  objetivo al frente **ni visible en ningún monitor** durante
  `segundos_fuera_app` (60 s) → alerta. Con `true`, debe estar al frente.
- **R2 · inactivo**: app presente pero `segundos_inactivo` (60 s) sin tocar
  nada → alerta (bájalo en `user.toml` si lo quieres más agresivo; súbelo si
  renderizas).
- **R0 · verificación con webcam (v0.2.1, opt-in)**: tu idea exacta. Con la
  cámara activada, `verificar_con_camara_seg` sin input dentro de la app
  (20 s por defecto; 120 s en la configuración de ejemplo) → **UNA foto** para
  verificar que sigues ahí (pensando el encuadre ≠ mirando el celular).
  Silenciosa y una sola vez por episodio: no alarma, no repite mientras no
  toques nada, y se rearma cuando vuelve el input. Umbral:
  `sesion.verificar_con_camara_seg` (0 = desactivada).
- **Ausencia (v0.5.0)**: pantalla bloqueada, suspensión o idle >
  `ausencia_seg` → el guardián se pausa solo y no dispara nada.
- `--aux` son apps toleradas (explorador, Bridge) que no cuentan como ausencia.
- **Declarar sin memorizar procesos (v0.6.0)**: la tarjeta **"Sesión de hoy"**
  del panel (tarea + programas + botón *Detectar apps (10 s)*) o
  `--detectar` en la CLI; el panel además permite **cambiarlas en vivo**, sin
  reiniciar el agente, y guardarlas como predeterminadas.
- Las apps aceptan regex simple: `light.?room` cubre Lightroom y Lightroom Classic.
- Mientras cumples: **cero capturas, cero nube, cero coste**. Al disparar una
  regla se toma UNA captura de evidencia (`capturar_al_disparar = false` para
  desactivarla) — y si la webcam está habilitada, también UNA foto de
  constancia — y arranca la escalera gradual (aviso → toast → voz), con el
  mismo enfriamiento de 5 min y tope de 4 alertas/hora del pipeline normal.
- Las pausas (`pause`, Pomodoro, `Ctrl+Alt+F12`) silencian al guardián y no
  cuentan como ausencia.

**Ajuste fino**: renders o exportados largos con la app abierta dispararán R2;
súbelo a 120-180 s en `user.toml` (`[sesion] segundos_inactivo = 150`).

### Webcam de verificación (v0.2.1, opt-in)

La cámara **no se queda encendida**: se abre, captura UN frame, se cierra. La
lámpara se enciende 1-2 s por foto y cada foto queda registrada en la base con
su motivo. Para activarla:

```toml
# config/user.toml
[camara]
habilitada = true
```

Prueba primero `python run.py test-cam` (una foto a `data/fotos/<día>/`) y
ajusta `indice` si tienes varias cámaras. Fotos guardadas con reescala a 640 px
y poda a los `retencion_dias` (7); `guardar_fotos = false` si prefieres que la
foto viva solo en RAM. Cada foto se registra en SQLite (`camara:<motivo>:<kb>kb`),
nunca en ventanas excluidas ni en modo privado, y el contador aparece en el
cierre de sesión.

### Ausencia, respuesta y traer-al-frente (v0.5.0)

Tres correcciones nacidas de revisar el flujo completo:

- **Si no estás, el agente no te reclama.** Con `sesion.ausencia_seg = 300`
  (0 = desactivado) se detecta pantalla bloqueada (`Win+L`, UAC, salvapantallas),
  suspensión del equipo o idle largo, y el guardián **se pausa solo**; al volver
  se reanuda limpio, sin arrastrar el episodio ni disparar la escalera de golpe.
- **La pregunta tiene respuesta.** Al abrir un episodio la mascota muestra una
  ventana con tres botones: *Sigo aquí*, *Pausa 10 min* y *Estoy leyendo*.
  "Estoy leyendo" da 5 min de gracia al reloj de inactividad (leer es trabajo)
  sin relajar la regla de "fuera de la app". Los mismos gestos existen como
  atajos (`Ctrl+Alt+F11` / `Ctrl+Alt+F10`) y como `run.py sigo`.
- **El "traer al frente" ya no interrumpe a los 30 s.** Exige
  `alertas.traer_al_frente_tras` llamados **con peso** (toast o voz, no el aviso
  sutil) y `alertas.minutos_antes_de_traer` (2 min) de desvío sostenido. Cuando
  ocurre, el asistente dice "Es momento de seguir trabajando".
- **Ancla estricta opcional**: `sesion.exigir_primer_plano = true` hace que una
  app visible en el otro monitor **no** cuente como presente (tu petición
  literal "quiero que Lightroom esté al frente"); por defecto sigue siendo
  tolerante para consultar referencias.

### Panel del Guardián (v0.3.0): configuración visual

El panel es una página local (solo accesible desde tu equipo, `127.0.0.1`) con
la estética que pediste: **claro greige/beige — nunca blanco — y banda oscura**
para las prohibiciones, con tema claro/oscuro conmutable. Ahí se configura
todo sin editar archivos:

- **Frecuencia de monitoreo** (slider 5-60 s) con derivados al estilo de la
  calculadora de la imagen: capturas/hora, ventana FIFO y RAM estimada.
- **Pantalla principal**: con dos monitores, elige de cuál se captura para el
  análisis visual. La detección de primer plano e inactividad es global
  (una sola ventana al frente en todo el sistema), y una app visible en el
  otro monitor sigue contando como presente.
- **Tiempos de intervención** (30 s - 5 min en sliders): desvío sostenido del
  modo monitoreo y reglas R1/R2 de la sesión.
- **Modo de aviso**: `solo visual` (mascota y notificaciones, sin sonido),
  `visual + sonido`, o `completo`: tras el **2.º o 3.er llamado** del episodio,
  tu app de trabajo (p. ej. Lightroom) **vuelve al frente automáticamente**.
  Si no fijas app objetivo, se usa la 1.ª app de la sesión activa.
- **Mascota**: visible on/off y tema (clásico greige / oscuro / cálido).
- **Sesión de hoy (v0.6.0)**: tarea, programas de trabajo, toleradas,
  **Iniciar / Cerrar sesión** y **Detectar apps (10 s)**.
- Botones de acción: pausar, reanudar, probar avisos, detener.

Los cambios se guardan en `config/user.toml` y **se aplican en vivo**: el
agente los recarga al ciclo siguiente (≤ 15 s) sin reiniciar. Nada sale a la
red: el panel solo escucha en localhost.

### Prohibiciones con presupuesto diario (v0.3.0)

"No permitir YouTube 1 hora, o redes sociales", implementado como presupuesto:

- Se cuenta el **tiempo de primer plano** por patrón (proceso o título, regex
  simple): YouTube en el navegador cuenta aunque el proceso sea Chrome.
- **Sin capturas**: solo mira la ventana activa, como el modo sesión.
- Sobrevive reinicios (tabla `presupuesto` en SQLite) y **caduca al día
  siguiente** — cada día vuelve a cero.
- Al agotarse: toast (una vez) y, si activas el **bloqueo**, la app se
  **minimiza cada vez que vuelve al frente** hasta mañana. Sin bloqueo, solo
  avisa y la barra del panel se pone en color de alarma.
- Máximo 12 patrones; en ventanas excluidas (banca, contraseñas) no se cuenta
  absolutamente nada.

Se añaden con un clic (chips de YouTube/Instagram/TikTok/Netflix) o a mano en
la banda oscura del panel; también en `user.toml`:

```toml
[prohibiciones]
lista = [
  { patron = "youtube",   limite_min_dia = 60, bloqueo_activo = true },
  { patron = "instagram", limite_min_dia = 30, bloqueo_activo = false },
]
```

### Mascota agente (v0.3.0)

La guardiana de escritorio (tkinter, sin dependencias nuevas): siempre visible,
arrastrable, y un clic abre el panel. Refleja el estado en tiempo real —
dormida cuando espera, atenta en foco, **rebota y muestra un anillo cuando hay
desvío**, con taza en las pausas — y los avisos de la escalera aparecen como
burbuja de texto sobre su cabeza.

**¿Se puede cambiar la apariencia?** Sí: elige tema en el panel (clásico
greige, oscuro, cálido) o añade el tuyo con tus colores en `mascota.py`
(tabla `TEMAS`). Y desde la v0.6.0 puedes ponerle **la cara de OpenPets**
(ver abajo). Pruébala sin agente:

```bat
python run.py mascota --demo --tema calido
```

### Avatar: OpenPets o la mascota integrada (v0.6.0)

El motor habla con un `Avatar` (interfaz común en `yourfocusguard/avatar/`) y
la configuración decide qué hay detrás:

```toml
[avatar]
proveedor = "auto"   # auto | openpets | tk | ninguno
frases = true        # burbujas de texto
```

- **`auto`** (recomendado): intenta **OpenPets**; si no está abierto o no
  responde, usa la mascota tkinter. Nunca te quedas sin asistente.
- **`openpets`**: solo OpenPets. Si no está, el asistente queda sin cara (los
  toasts, la voz y el panel siguen funcionando).
- **`tk`**: solo la mascota integrada (comportamiento anterior).
- **`ninguno`**: sin cara; consola, toasts y voz.

**Cómo se conecta** (sin escribir TypeScript, sin red): OpenPets publica un
IPC local con token en `%APPDATA%\OpenPets\runtime\ipc.json`. El cliente de
`yourfocusguard/avatar/openpets.py` lee ese archivo y envía JSON por el named
pipe (o TCP en WSL) usando tres métodos: `hello`, `pet.react` y `pet.say`.
Mapeo de estados: FOCO→`working`, ESCALADA→`error`, PAUSA→`waiting`,
EN_ESPERA→`idle`; cada aviso va como burbuja de una línea (máx. 140
caracteres, sin URLs). Los envíos van por cola y hilo propios, así que un
OpenPets colgado jamás bloquea la vigilancia.

Instala OpenPets desde sus
[releases](https://github.com/OpenPetsHQ/openpets/releases) y déjalo abierto;
el panel te dice qué cara está activa.

**Limitación conocida**: por el IPC público la pregunta contextual va como
burbuja **sin botones** (se responde con `Ctrl+Alt+F11/F10` o `run.py sigo`).
Los botones siguen en la mascota tkinter; el chat y la voz llegarán con el Pet
Assistant de OpenPets en la Fase 3.

**¿Y VPet?** Es precioso (384 animaciones) pero su API es un plugin en C#/.NET
y no expone un canal para procesos externos: integrarlo sería mantener un
segundo runtime. Puede convivir como decoración, pero no reacciona al estado.

### Perfiles de máquina (tabla 8 del blueprint)

- `python run.py start` — perfil **pc** (completo): nube cada 60 s, captura cada 15 s
- `python run.py start --profile laptop` — perfil **laptop** (ligero): solo heurística
  local, captura cada 20 s, cero coste de API
- `python run.py start --privado` — modo privado: apaga la nube aunque el perfil la tenga

## Configuración

Todo vive en `config/` y se lee por capas: `default.toml` → `pc.toml`/`laptop.toml` →
**`user.toml`** (tus ajustes; hay plantilla en `user.toml.example`). Los valores por
defecto son los de la tabla 5 del blueprint:

| Parámetro | Defecto | Nota |
|---|---|---|
| `captura.intervalo_seg` | 15 | una captura por ciclo |
| `captura.fifo_frames` | 5 | ventana efectiva 45-75 s |
| `alertas.desvio_sostenido_seg` | 30 | 20-60 recomendado; el panel permite hasta 300 |
| `alertas.modo` | completo | visual / visual_sonoro / completo (panel) |
| `alertas.traer_al_frente_app` | "" | modo completo: app que vuelve al frente; "" = 1.ª de la sesión |
| `alertas.traer_al_frente_tras` | 2 | tras el 2.º o 3.er llamado **con peso** (toast/voz) |
| `alertas.minutos_antes_de_traer` | 2.0 | además, el desvío debe llevar este tiempo |
| `alertas.aviso_seg / toast_seg / voz_seg` | 30 / 60 / 90 | escalera |
| `alertas.enfriamiento_seg` | 300 | silencio tras la voz |
| `alertas.tope_por_hora` | 4 | protección anti-acoso |
| `cerebro.proveedor_nube` | gemini | gemini / openai / ninguno |
| `cerebro.presupuesto_diario_usd` | 0.75 | corte automático de nube |
| `sesion.segundos_fuera_app` | 60 | R1 del modo sesión (20-300 razonable) |
| `sesion.segundos_inactivo` | 60 | R2 del modo sesión; súbelo si renderizas |
| `sesion.intervalo_sondeo` | 5 | cadencia del sondeo con sesión activa |
| `sesion.capturar_al_disparar` | true | evidencia única al disparar |
| `sesion.verificar_con_camara_seg` | 20 | R0: foto de webcam tras N s congelado; 0 = off |
| `sesion.ausencia_seg` | 300 | pantalla bloqueada / suspensión / idle largo → pausa sola; 0 = off |
| `sesion.exigir_primer_plano` | false | true = la ancla debe estar AL FRENTE (no vale otro monitor) |
| `sesion.monitor_objetivo` | 0 | 0 = cualquiera; 1..N = la ventana al frente debe estar en ese monitor |
| `sesion.apps` | [] | anclas del Modo Anclado (panel/TOML; se recargan en vivo) |
| `avatar.proveedor` | auto | auto / openpets / tk / ninguno |
| `avatar.frases` | true | burbujas de texto en el avatar |
| `prohibiciones.lista` | [] | presupuestos diarios por patrón (panel) |
| `mascota.visible` | true | la guardiana en el escritorio |
| `mascota.tema` | clasico | clasico / oscuro / calido |
| `panel.activo` | true | panel web con `start`; `--sin-panel` lo salta |
| `panel.puerto` | 8756 | solo 127.0.0.1, nunca la red |
| `camara.habilitada` | false | opt-in: la webcam solo se abre para UNA foto |
| `camara.indice` | 0 | webcam por defecto; prueba con `test-cam` |
| `camara.guardar_fotos` | true | false = la foto vive solo en RAM |
| `camara.retencion_dias` | 7 | poda de `data/fotos` (carpetas por día) |
| `concentracion.habilitado` | false | modo máxima concentración (v0.7.0) |
| `concentracion.bloquear_hosts` | true | reescribir archivo hosts de Windows |
| `concentracion.silenciar_audio` | true | mute del dispositivo de salida por defecto |
| `concentracion.dominios` | [] | dominios a bloquear (vacío = lista predeterminada) |
| `concentracion.apps_bloqueadas` | [] | procesos a minimizar al frente |
| `concentracion.restaurar_al_salir` | true | deshacer hosts/audio al cerrar sesión |
| `presencia.habilitada` | false | detección de rostro/teléfono con MediaPipe (opt-in) |
| `presencia.indice_camara` | 0 | índice de la webcam a usar |
| `presencia.intervalo_seg` | 30 | cada cuántos segundos comprobar |
| `presencia.ausente_para_pausar_seg` | 120 | sin rostro durante N s → pausa la sesión; 0 = off |
| `presencia.telefono_en_mano_seg` | 10 | teléfono detectado durante N s → aviso |
| `heuristica.apps_distraccion` | lista | edítala con lo que te distrae a TI |
| `privacidad.titulos_excluidos` | lista | banca, contraseñas, navegación privada |
| `privacidad.atajo_sigo` | ctrl+alt+f11 | "sigo en la tarea" (cierra el aviso) |
| `privacidad.atajo_pausa_corta` | ctrl+alt+f10 | pausa corta a pedido |
| `privacidad.pausa_corta_min` | 10 | minutos de la pausa corta |

**Consejo**: pasa 10 minutos con `python run.py inspect` mientras trabajas y vuelca
lo que veas en `user.toml`. El Nivel B solo es bueno si tus listas reflejan tu vida real.

## Privacidad (cap. 7 del blueprint, resumen)

- **Las imágenes nunca tocan el disco**: viven como bytes en RAM, máx. 75 s, y se
  sobreescriben. No hay archivo de capturas que filtrar.
- Lo que viaja a la nube: solo el lote de 2 frames del ciclo y el prompt del sistema.
  Nunca viajan la base SQLite, rutas ni configuración.
- **Exclusiones**: ventanas que coinciden con `privacidad.*` ni se capturan ni se
  evalúan; el agente entra en pausa "privado" hasta que cambies de ventana.
- **La webcam (v0.2.1) es opt-in y solo por eventos**: `verificar_con_camara_seg`
  de congelamiento dentro de una sesión (20 s por defecto), o una regla disparada. Captura un único frame y libera
  la cámara; jamás en ventanas excluidas ni en modo privado. Las fotos viven en
  `data/fotos/<día>/` con poda automática (o solo en RAM con `guardar_fotos =
  false`); cada toma queda registrada en la base con su motivo.
- Los eventos en SQLite (`data/yourfocusguard.db`) guardan decisiones (app, título,
  estado, confianza), no evidencia visual. Poda automática a los 180 días.
- `python run.py purge --si` borra todo lo registrado.
- Modo privado (`--privado`): ni una imagen sale del equipo.

## Coste del Nivel A

Con los valores por defecto (análisis cada 60 s, 2 imágenes), el gasto estimado es
de 0,4-0,8 USD por jornada de 8 h (entre 8 y 15 USD/mes, cap. 4 del blueprint).
El contador `cerebro.presupuesto_diario_usd` corta la nube automáticamente al pasar
el tope y el agente sigue con la heurística local. Verifica los precios vigentes de
tu proveedor: son estimaciones de orden de magnitud.

## Estructura del proyecto

```
YourFocusGuard/
├── run.py                    # CLI (start/panel/mascota/pause/status/doctor/...)
├── config/                   # default.toml + pc.toml + laptop.toml + user.toml
├── yourfocusguard/
│   ├── config.py             # carga TOML por capas + recarga en vivo + escritor user.toml
│   ├── engine.py             # motor: estados, Pomodoro, pausas, sesión, prohibiciones, medidas
│   ├── session_guard.py      # guardián de tarea: R1/R2 por predicados (v0.2.0)
│   ├── vigilante.py          # prohibiciones: presupuestos diarios por primer plano (v0.3.0)
│   ├── mascota.py            # agente mascota: temas, estados, burbuja (v0.3.0)
│   ├── avatar/               # cara intercambiable: OpenPets IPC / tk / ninguno (v0.6.0)
│   ├── panel.py              # Panel del Guardián: API + estáticos (v0.3.0)
│   ├── panel_static/         # index.html + estilos.css + aplicacion.js
│   ├── console_ui.py         # líneas de estado coloreadas
│   ├── capture/              # mss, ventana activa, ventanas visibles multi-monitor, monitores, idle y webcam
│   ├── memory/               # FIFO de 5 frames + FrameSnapshot
│   ├── brain/                # prompts v1, heurística B, gemini, openai, router
│   ├── actions/              # escalera, toast, TTS, beep, notifier, traer-al-frente/minimizar
│   ├── privacy/              # exclusiones
│   └── storage/              # SQLite (Apéndice B + migraciones 001-002)
├── tests/                    # 199 tests (pytest)
└── data/                     # se crea al correr: db, logs, state.json, control.json, fotos/
```

## Desarrollo

```bat
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

Los tests cubren la lógica pura (máquina de estados, escalera, router, caché,
disyuntor, presupuesto, base de datos) con relojes y capturadores falsos: no
necesitan Windows, pantalla ni claves de API.

## Solución de problemas

| Síntoma | Qué revisar |
|---|---|
| La webcam no aparece en `doctor` / `test-cam` falla | ¿Otra app (Zoom, OBS) la tiene ocupada? Ciérrala. Si tienes varias cámaras, prueba `indice = 1` en `[camara]`. Verifica también que `pip install opencv-python-headless` se ejecutó. |
| La foto de verificación sale a oscuras | Sube `camara.preframes` (10-12) para dar más tiempo a la exposición automática. |
| La foto de verificación me molesta | Baja la frecuencia con `verificar_con_camara_seg = 40-60`, o apágala del todo: `habilitada = false` (o `verificar_con_camara_seg = 0`). |
| El modo sesión avisa cuando renderizo/exporto | Es R2 (inactivo). Sube `sesion.segundos_inactivo` a 120-180 en `user.toml`, o declara la app de render en `--aux`. |
| El panel no abre (puerto ocupado) | `python run.py panel --puerto 8757`, o mira qué otro panel quedó abierto. |
| La mascota no aparece | Necesita Windows con escritorio (tkinter viene con Python). En SSH/servidor se desactiva sola; prueba `python run.py mascota --demo`. |
| OpenPets no reacciona | Comprueba que está abierto (escribe `%APPDATA%\OpenPets\runtime\ipc.json`), que `[avatar] proveedor` no es `"tk"`, y mira "Cara activa" en el panel. Si está en `openpets` y no responde, el asistente se queda sin cara a propósito; con `auto` cae a la mascota. |
| Cambié las apps y el agente sigue con las viejas | Las apps del panel se aplican en vivo (≤ 5 s). Si declaraste la sesión a mano con `--apps`, esa manda hasta cerrarla (`run.py session stop`). |
| Las prohibiciones no cuentan | El conteo corre **con el agente arrancado** (`start`), por primer plano. En ventanas excluidas no se cuenta a propósito. |
| El "traer al frente" no encuentra mi app | Escribe el nombre del proceso sin `.exe` (Lightroom: `lightroom`; a veces `lightroomclassic`). El botón Probar avisos del panel te dice si la ventana se encontró. |
| El modo sesión avisa aunque la app está abierta en el otro monitor | Con `sesion.exigir_primer_plano = true` eso es intencional. Si solo estás consultando referencias, ponlo en `false` o agrega la app a `apps_auxiliares`. |
| Me avisa con la pantalla bloqueada o al volver del almuerzo | Actualiza a v0.5.0: `sesion.ausencia_seg` (300 s) detecta bloqueo, suspensión e idle largo y pausa sin avisar. Si lo quieres más tarde, súbelo; `0` lo desactiva. |
| La pregunta aparece pero no sé cómo contestar | Pulsa un botón de la ventana de la mascota, o usa `Ctrl+Alt+F11` (sigo), `Ctrl+Alt+F10` (pausa corta) o `python run.py sigo`. Si la mascota está oculta, quedan los atajos y la CLI. |
| Me trae la app al frente demasiado pronto | Sube `alertas.minutos_antes_de_traer` (2 min por defecto) o `alertas.traer_al_frente_tras`; con `modo = "visual"` no se trae ninguna ventana. |
| Las fotos de webcam no se guardan | Corregido en v0.5.0 (el motivo traía `:` y Windows lo rechaza). Si persiste, revisa permisos de `data/fotos` y el log. |
| No hay voz | `python run.py doctor` lista las voces. Si no hay ninguna en español: Configuración → Hora e idioma → Voz → añadir paquete de voz español. Luego fija `alertas.tts_voz` en `user.toml`. |
| No aparecen toasts | Windows: Configuración → Sistema → Notificaciones (activadas para tu usuario). El "asistente de concentración" puede silenciarlas. |
| `doctor` dice que falta `GEMINI_API_KEY` | Copia `.env.example` a `.env` (mismo nombre, sin "example") y pega la clave. |
| La nube nunca se usa | Mira el log (`data/logs/agente.log`): si ver `disyuntor_abierto` o `presupuesto_agotado`, el router está protegiéndote; la heurística sigue opinando. |
| Detecta de menos | Tus listas de `heuristica` están cortas: corre `run.py inspect` y completa `user.toml`. O baja `alertas.desvio_sostenido_seg` a 20-25. |
| Detecta de más | Sube `desvio_sostenido_seg` a 40-60, o quita apps de `apps_distraccion` que en tu caso son trabajo (p. ej. WhatsApp). |
| Muchos avisos en días malos | Es el tope de 4/hora trabajando; puedes bajarlo a 2 en `[alertas] tope_por_hora`. |
| YouTube a pantalla completa no avisa | Es la regla 2 del blueprint (modo silencioso automático). Si quieres que avise igual: `alertas.silenciar_pantalla_completa = false`. |

## Hoja de ruta (desde el blueprint)

- **F3 — Webcam analítica** (restante): MediaPipe, las tres detecciones (celular en
  mano, conversación, mirada fuera del cono ±25-30°), análisis opcional de las
  fotos de verificación con el Nivel A. La base (captura bajo demanda) ya está
  en v0.2.1.
- **F4 — Local y laptop** (restante): SmolVLM/Moondream en CPU (Nivel C), icono
  de bandeja, empaquetado con PyInstaller y autoarranque. La mascota de
  escritorio ya está (v0.3.0, tkinter + temas).
- **F5 — Endurecimiento**: reporte semanal, calibración de umbrales con datos reales,
  poda avanzada.

## Licencia

MIT (ver `LICENSE`). El blueprint de arquitectura que da origen a este código es
tu documento de diseño; los repositorios citados en su Apéndice A son referencias
de ideas, no dependencias.
