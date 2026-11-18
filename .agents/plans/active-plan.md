# Plan: Selector de Perfiles de Trabajo Móvil (Edición de Fotos / Vibe Coding)

## Contexto
El usuario requiere que en el widget móvil del celular (Nubia Z17 Lite), al presionar "Iniciar Trabajo", se desplieguen directamente sus dos perfiles principales:
1. **📸 Editar Fotos**: Lightroom, Lightroom Classic, Photoshop (aux: Explorer, Bridge).
2. **💻 Vibe Coding**: VS Code, Cursor, Windsurf, Antigravity, Terminales (aux: Navegadores).

## Arquitectura de Solución
1. **Selector de Perfiles en `widget-mascota.html/.js`**:
   - **Estado Inactivo**: Botón `[ 🚀 Iniciar Trabajo ]` que al tocarse despliega modal/selector táctil:
     - Opción A: `[ 📸 Editar Fotos ]`
     - Opción B: `[ 💻 Vibe Coding ]`
   - **Inicio de Sesión**: Envío a `/api/control` de `cmd: "session_start"` con `apps`, `aux` y `texto` específicos del perfil seleccionado.
   - **Estado Activo**: Chip/barra superior: `🟢 <Perfil Activo> · [ ⏹ Cerrar Sesión ]`.
   - **Feedback de Mascota**: Burbuja de diálogo reactiva confirmando el perfil iniciado.
2. **Control de Voz y Estado 8756**:
   - Feedback táctil e interactivo en pantalla al tocar `[ 🎤 ]`.
   - Conexión continua asegurada entre 8770 y 8756.

## Perfiles Predefinidos
- `perfil_fotos`: `texto: "Edición de Fotos"`, `apps: ["lightroom", "lightroomclassic", "photoshop"]`, `aux: ["explorer", "bridge"]`.
- `perfil_coding`: `texto: "Vibe Coding"`, `apps: ["code", "cursor", "windsurf", "antigravity", "terminal", "powershell", "cmd"]`, `aux: ["chrome", "brave", "edge", "firefox"]`.

## Archivos Afectados
- `adhd-assistant/app/ui/widget-mascota.html`: contenedor selector de perfiles y barra de sesión activa.
- `adhd-assistant/app/ui/widget-mascota.css`: estilos de tarjetas/botones táctiles de perfiles y chip de estado.
- `adhd-assistant/app/ui/widget-mascota.js`: lógica de selección de perfil, envío de `session_start` / `session_stop` y polling de estado de sesión.

## Checklist de Implementación
- [ ] 1. Diseñar componente selector de perfiles táctil en `widget-mascota.html`.
- [ ] 2. Añadir estilos responsivos en `widget-mascota.css` para botones de perfil y barra de sesión activa.
- [ ] 3. Programar lógica de activación por perfil (`fotos` vs `coding`) en `widget-mascota.js` conectada a `/api/control`.
- [ ] 4. Sincronizar estado de sesión en tiempo real (mostrar perfil activo y botón para finalizar).
- [ ] 5. Probar y verificar en el puerto 8770 / widget móvil.
