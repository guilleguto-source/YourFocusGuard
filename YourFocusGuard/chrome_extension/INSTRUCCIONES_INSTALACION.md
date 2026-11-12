# YourFocusGuard — YouTube Audio Defocus Extension

Esta extensión ligera para Google Chrome (Manifest V3) permite escuchar música y podcasts en YouTube durante sesiones de foco sin distracciones visuales.

## ¿Qué hace?
- Se conecta en tiempo real a tu servidor local de YourFocusGuard (`127.0.0.1:8756`).
- Cuando una sesión de trabajo o foco está activa en Lightroom, Photoshop o programación:
  - Aplica automáticamente un **desenfoque gaussiano profundo** (`blur(28px)`) y desaturación sobre el video.
  - Coloca un overlay suave que indica *"🐾 Modo Foco Activo: Audio sonando en segundo plano"*.
  - **El audio nunca se corta ni se interrumpe**.
- Cuando pausas o cierras la sesión, el video vuelve a la normalidad de forma instantánea.

---

## Cómo instalarla en Chrome (solo toma 30 segundos)

1. Abre Google Chrome y escribe en la barra de direcciones:
   ```
   chrome://extensions
   ```
2. En la esquina superior derecha, activa el interruptor **"Modo de desarrollador"**.
3. Haz clic en el botón **"Cargar descomprimida"** (Load unpacked) que aparecerá a la izquierda.
4. Selecciona la carpeta:
   ```
   C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard\chrome_extension
   ```
5. ¡Listo! La extensión ya estará activa y funcionando en conjunto con tu asistente.
