# Fase 0 (v0.5.0): cómo probarla en 10 minutos

Guía corta para verificar en tu equipo que el agente ya no te reclama cuando no
estás y que sí te escucha cuando te reclama. Todo pasa en
`ADHD Assistant/YourFocusGuard/`.

## Antes de empezar

```bat
cd "C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard"
.venv\Scripts\activate
python run.py doctor
```

`doctor` debe decir **[OK]** en "Idle de entrada" (si dice "no disponible" es
que estás en otra versión: la v0.5.0 lo corrige) y **[OK]** en "Captura de
pantalla" con la nota "no se usa en Modo Anclado".

Revisa `config/user.toml`: ya viene con tus anclas (`lightroom`,
`lightroomclassic`, `photoshop`), 60 s de fuera/inactivo, 2 min para la foto,
5 min de ausencia y `exigir_primer_plano = true`. Si prefieres tolerar
referencias en el segundo monitor, ponlo en `false`.

## Arrancar

```bat
python run.py start
```

Se abre el panel en `http://127.0.0.1:8756` y la mascota en la esquina.

## Las cinco pruebas

| # | Qué haces | Qué debe pasar |
|---|---|---|
| 1 | Cambias a Chrome (Lightroom abierto, primer plano perdido) y esperas 1 min | La mascota pregunta: "Ya no estás en lightroom, lightroomclassic, photoshop. ¿Volvemos a la tarea?" y aparece la ventanita con botones |
| 2 | Pulsas **"Sigo aquí"** | El aviso se cierra en ≤ 5 s, no suena la voz y no vuelve a insistir en el siguiente minuto |
| 3 | Te quedas quieto en Lightroom 1 min (sin tocar nada) | Pregunta por inactividad ("¿Qué estás haciendo?"). Pulsas **"Estoy leyendo"** y no te vuelve a molestar 5 min |
| 4 | Bloqueas Windows (`Win+L`) y vuelves a los 3 min | Ningún aviso, ninguna foto. En `python run.py status` ves `pausa: ausencia`; al volver, el estado sale de pausa solo |
| 5 | Ignoras el aviso ~2 min (modo `completo`) | Pasado el toast + la voz y los 2 min de `minutos_antes_de_traer`, Lightroom vuelve al frente y dice "Es momento de seguir trabajando" |

Si quieres ver el "traer al frente" sin esperar, baja `minutos_antes_de_traer`
a `0.5` en `config/user.toml` (se aplica en vivo, ≤ 15 s).

## Atajos y CLI

- `Ctrl+Alt+F12` pausa / reanuda.
- `Ctrl+Alt+F11` = "sigo aquí" (sin abrir nada).
- `Ctrl+Alt+F10` = pausa corta (10 min).
- `python run.py sigo` / `python run.py pause 10` / `python run.py resume`.
- `python run.py status` muestra el estado, la pausa y el resumen del día.

## Si algo no cuadra

- **No aparece la ventanita de la pregunta**: la mascota está oculta
  (`[mascota] visible = false`) o no hay escritorio; usa `Ctrl+Alt+F11`.
- **Me avisa al volver del café**: sube `sesion.ausencia_seg` (p. ej. 600) o
  revisa que el `idle` de `doctor` funcione.
- **Me trae al frente demasiado pronto**: sube `minutos_antes_de_traer` o
  `traer_al_frente_tras`; con `modo = "visual"` no trae ventanas.
- **La cámara no guarda**: `[camara] habilitada = true` y `python run.py test-cam`.
  Las fotos van a `data/fotos/<día>/` y se podan a los 7 días.

## Lo que NO cambia todavía

- No hay capturas de pantalla ni nube en Modo Anclado (por diseño).
- No hay detección de celular ni de "no estás en la silla" con visión: eso es F3.
- El diálogo es una pregunta con botones, no una conversación: eso llega con el
  avatar (OpenPets) en la Fase 2.
