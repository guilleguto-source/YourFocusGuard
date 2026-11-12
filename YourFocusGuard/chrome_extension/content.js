// YourFocusGuard - Extension de Desenfoque Inteligente de YouTube (v1.0.0)
(function() {
  const PANEL_URL = "http://127.0.0.1:8756/api/estado";
  let focoActivo = false;
  let overlayElement = null;

  function aplicarFiltro(activo) {
    const video = document.querySelector("#movie_player video, video.html5-main-video");
    const container = document.querySelector("#movie_player");

    if (activo) {
      if (video) {
        video.style.filter = "blur(28px) grayscale(85%)";
        video.style.transition = "filter 0.4s ease";
      }
      if (container && !document.getElementById("yfg-focus-overlay")) {
        overlayElement = document.createElement("div");
        overlayElement.id = "yfg-focus-overlay";
        overlayElement.style.position = "absolute";
        overlayElement.style.inset = "0";
        overlayElement.style.zIndex = "99";
        overlayElement.style.pointerEvents = "none";
        overlayElement.style.display = "flex";
        overlayElement.style.flexDirection = "column";
        overlayElement.style.alignItems = "center";
        overlayElement.style.justifyContent = "center";
        overlayElement.style.background = "rgba(24, 23, 22, 0.45)";
        overlayElement.style.color = "#F5F5F0";
        overlayElement.style.fontFamily = "system-ui, sans-serif";
        overlayElement.innerHTML = `
          <div style="padding: 12px 24px; background: rgba(0,0,0,0.7); border-radius: 12px; border: 1px solid #7A8B6F; text-align: center;">
            <div style="font-weight: 700; font-size: 15px; margin-bottom: 4px;">🐾 Modo Foco Activo</div>
            <div style="font-size: 12px; opacity: 0.9;">Video desenfocado · Audio sonando en segundo plano</div>
          </div>
        `;
        container.appendChild(overlayElement);
      }
    } else {
      if (video) {
        video.style.filter = "none";
      }
      const existing = document.getElementById("yfg-focus-overlay");
      if (existing) existing.remove();
    }
  }

  // Consultar estado al servidor local del asistente
  async function verificarFoco() {
    try {
      const resp = await fetch(PANEL_URL, { cache: "no-store" });
      if (resp.ok) {
        const data = await resp.json();
        const sesion = data.session || data.estado || {};
        const estaEnSesion = (sesion.estado === "FOCO" || data.estado === "FOCO") && Boolean(sesion.activa);
        
        // Si hay sesión de edición o trabajo activa, activar el desenfoque
        if (estaEnSesion !== focoActivo) {
          focoActivo = estaEnSesion;
          aplicarFiltro(focoActivo);
        }
      }
    } catch (e) {
      // Backend no disponible
    }
  }

  // Verificar cada 3 segundos
  setInterval(verificarFoco, 3000);
  verificarFoco();
})();
