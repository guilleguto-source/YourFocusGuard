# Fases 1 y 2 (v0.6.0): cómo probarlas

## Fase 1 · Declarar la sesión (sin consola)

1. Arranca el agente: `python run.py start` y abre el panel
   (`http://127.0.0.1:8756`).
2. En **"Sesión de hoy"** escribe la tarea ("editar fotos de la boda").
3. Pulsa **Detectar apps (10 s)** y, durante esos 10 s, cambia a Lightroom y
   muévete un poco. El campo se rellena con las apps que vio (`lightroom`,
   `photoshop`…). Las apps "neutras" (terminal, explorador) se filtran solas.
4. Pulsa **Iniciar sesión**. El chip de la cabecera pasa a "en tarea" y la
   tarjeta muestra las anclas activas.
5. Prueba el cambio en vivo: borra `photoshop` del campo, pulsa
   **Guardar y aplicar** y mira la consola: en ≤ 5 s aparece
   `anclas actualizadas en vivo: …` sin reiniciar nada.
6. **Cerrar sesión** termina la sesión y muestra el resumen.

Notas:

- Si declaras la sesión a mano (`run.py session start --apps x`), esas anclas
  mandan sobre `user.toml` hasta que cierres la sesión.
- `sesion.monitor_objetivo = 2` exige además que la ventana al frente esté en
  el monitor 2 ("trabajo siempre en el segundo").

## Fase 2 · La cara de OpenPets

1. Descarga e instala OpenPets:
   <https://github.com/OpenPetsHQ/openpets/releases> (Windows, instalador
   firmado). Ábrelo: debe aparecer su mascota.
2. Comprueba que dejó su archivo de descubrimiento:
   `%APPDATA%\OpenPets\runtime\ipc.json`.
3. En `config/user.toml` deja (o pon):
   ```toml
   [avatar]
   proveedor = "auto"
   frases = true
   ```
4. Reinicia el agente. En el panel, la tarjeta **Mascota agente** debe decir
   **"Cara activa: OpenPets"**.
5. Prueba las reacciones:
   - Empieza a trabajar → `working`.
   - Salte de la app 1 min → burbuja con la pregunta y reacción `error`.
   - Pausa (`Ctrl+Alt+F12`) → `waiting`.
   - El cierre de sesión todavía no tiene reacción propia (se queda en `idle`).
6. **Fallback**: cierra OpenPets y reinicia el agente. Debe aparecer la
   mascota tkinter y el panel decir "Cara activa: mascota integrada". Si
   `proveedor = "openpets"`, en cambio, te quedas sin cara (a propósito).

### Qué se puede y qué no

| Acción | OpenPets | Mascota tkinter |
|---|---|---|
| Reaccionar al estado | sí (`pet.react`) | sí (sprites) |
| Decir frases / avisos | sí (`pet.say`, burbuja) | sí (burbuja) |
| Preguntar con botones | **no** (solo burbuja) | sí |
| Responder | atajos / `run.py sigo` | botones o atajos |
| Cambiar el look | galería de OpenPets | temas `TEMAS` |

La elección de cara ocurre **al arrancar** el agente: si abres OpenPets
después, reinicia el agente para que la use (o deja `auto` y ábrelo antes).

## Lo que sigue (Fase 3)

- Plugin "Focus Bridge" para OpenPets: el Pet Assistant podrá preguntar
  "¿qué toca hoy?", arrancar la sesión y contarte el resumen, con chat y voz.
- Modo máxima concentración de verdad (mute + bloqueo de dominio).
- MediaPipe para "no estás en la silla" y "celular en mano".
