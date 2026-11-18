/* Widget de Mascota Einstein Grande — Asistente TDAH (v0.13.0)
   Panel táctil dedicado para el celular (Nubia Z17 Lite / Desk Panel) */
"use strict";

const $ = (sel) => document.querySelector(sel);

/* ---------------- Utilidades ---------------- */

async function api(metodo, ruta, cuerpo) {
  const opciones = { method: metodo, headers: {} };
  if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  try {
    const resp = await fetch(ruta, opciones);
    const datos = await resp.json().catch(() => ({}));
    return { ok: resp.ok, estado: resp.status, datos };
  } catch (e) {
    return { ok: false, estado: 0, datos: {} };
  }
}

let toastTimer = null;
function toast(mensaje, largo = 2200) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = mensaje;
  el.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("visible"), largo);
}

/* ---------------- Mascota y Diálogo --------- */

let reaccionActual = "idle";
let ultimoTextoBurbuja = "";

/* ---------------- Perfiles de Trabajo Predefinidos ---------------- */
const PERFILES_TRABAJO = {
  fotos: {
    nombre: "Edición de Fotos",
    icono: "📸",
    apps: ["lightroom", "lightroomclassic", "photoshop"],
    aux: ["explorer", "bridge"],
  },
  coding: {
    nombre: "Vibe Coding",
    icono: "💻",
    apps: ["code", "cursor", "windsurf", "antigravity", "terminal", "powershell", "cmd"],
    aux: ["chrome", "brave", "edge", "firefox"],
  },
};

let sesionActivaLocal = false;

function renderizarEstadoSesion(activa, tarea) {
  sesionActivaLocal = Boolean(activa);
  const elInactiva = $("#sesion-inactiva");
  const elActiva = $("#sesion-activa");
  const elTxt = $("#tarea-activa-txt");
  const elSelector = $("#selector-perfiles");
  const elBtnIniciar = $("#btn-iniciar-trabajo");

  if (!elInactiva || !elActiva) return;

  if (sesionActivaLocal) {
    elInactiva.classList.add("oculta");
    elActiva.classList.remove("oculta");
    if (elTxt) {
      elTxt.textContent = tarea ? `${tarea}` : "En Foco";
    }
  } else {
    elActiva.classList.add("oculta");
    elInactiva.classList.remove("oculta");
    if (elSelector) elSelector.classList.add("oculta");
    if (elBtnIniciar) elBtnIniciar.classList.remove("oculta");
  }
}

async function iniciarPerfil(clave) {
  const p = PERFILES_TRABAJO[clave];
  if (!p) return;
  toast(`🚀 Iniciando: ${p.nombre}...`);
  fijarReaccion("working");
  actualizarBurbuja(`¡Modo ${p.nombre} activado! Protegiendo tu foco.`, []);
  renderizarEstadoSesion(true, p.nombre);

  const r = await api("POST", "/api/control", {
    cmd: "session_start",
    texto: p.nombre,
    apps: p.apps,
    aux: p.aux,
    minutos: 0,
  });

  if (!r.ok) {
    toast(`Fallo al iniciar sesión: ${r.datos?.error || "error"}`, 3000);
  } else {
    api("POST", "/api/phone/wake");
  }
}

async function cerrarSesionTrabajo() {
  toast("⏹ Cerrando sesión...");
  fijarReaccion("waving");
  actualizarBurbuja("Sesión finalizada. ¡Excelente trabajo!", []);
  renderizarEstadoSesion(false);

  const r = await api("POST", "/api/control", { cmd: "session_stop" });
  if (r.ok) {
    toast("Sesión finalizada con éxito");
  }
}

function normalizarOpcion(op) {
  if (Array.isArray(op)) {
    return String(op[1] || op[0] || "");
  }
  return String(op || "");
}

function actualizarBurbuja(texto, opciones) {
  const elTexto = $("#burbuja-texto");
  const elOpciones = $("#burbuja-opciones");
  if (!elTexto || !elOpciones) return;

  const txtLimpio = String(texto || "").trim();
  elTexto.textContent = txtLimpio || "¡Todo listo para avanzar con foco!";

  elOpciones.innerHTML = "";
  if (Array.isArray(opciones) && opciones.length > 0) {
    opciones.forEach((op) => {
      const etiqueta = normalizarOpcion(op);
      if (!etiqueta) return;
      const btn = document.createElement("button");
      btn.className = "burbuja-btn";
      btn.textContent = etiqueta;
      btn.type = "button";
      btn.addEventListener("click", () => responderOpcion(op));
      elOpciones.appendChild(btn);
    });
  }
}

async function responderOpcion(op) {
  const clave = Array.isArray(op) ? String(op[0]) : String(op);
  if (clave === "fotos" || clave === "coding") {
    iniciarPerfil(clave);
    return;
  }
  toast(`Enviando: ${normalizarOpcion(op)}...`);
  const r = await api("POST", "/api/pet/responder", { respuesta: clave });
  if (r.ok) {
    actualizarBurbuja("Entendido.", []);
  }
}

function fijarReaccion(reacc) {
  reaccionActual = reacc;
  document.documentElement.setAttribute("data-reaction-state", reacc);
}

async function actualizarEstadoMascota() {
  const r = await api("GET", "/api/pet/state");
  if (r.ok && r.datos) {
    const d = r.datos;

    // Estado de sesión
    const sesionActiva = Boolean(d.sesion_activa);
    let tarea = d.sesion_tarea || (d.sesion && d.sesion.texto) || "";
    if (!tarea && sesionActiva) {
      const apps = (d.sesion && d.sesion.apps) || [];
      if (apps.some((a) => ["lightroom", "lightroomclassic", "photoshop"].includes(String(a).toLowerCase()))) {
        tarea = "Edición de Fotos";
      } else if (apps.some((a) => ["code", "cursor", "windsurf", "antigravity"].includes(String(a).toLowerCase()))) {
        tarea = "Vibe Coding";
      }
    }
    renderizarEstadoSesion(sesionActiva, tarea);

    // Reacción del sprite
    const reacc = d.reaccion || "idle";
    if (reacc !== reaccionActual) {
      if (reacc === "alert" || reacc === "waiting") {
        api("POST", "/api/phone/wake");
      }
      fijarReaccion(reacc);
    }

    // Diálogo en burbuja
    const burbuja = d.burbuja || {};
    const txt = burbuja.texto || "";
    const ops = burbuja.opciones || [];
    if (txt !== ultimoTextoBurbuja || ops.length > 0) {
      if (ultimoTextoBurbuja && txt) {
        api("POST", "/api/phone/wake");
      }
      ultimoTextoBurbuja = txt;
      actualizarBurbuja(txt, ops);
    }
  }
}

/* ---------------- Botonera de Acciones en los Pies ------ */

async function accionControl(cmd, mensajeToast, tempReaction) {
  toast(mensajeToast);
  if (tempReaction) {
    fijarReaccion(tempReaction);
  }
  const r = await api("POST", "/api/control", { cmd });
  if (!r.ok) {
    await api("POST", "/api/pet/control", { cmd });
  }
}

function inicializarInteracciones() {
  // Selector de perfiles de trabajo
  const btnIniciarTrabajo = $("#btn-iniciar-trabajo");
  const elSelectorPerfiles = $("#selector-perfiles");
  if (btnIniciarTrabajo) {
    btnIniciarTrabajo.addEventListener("click", () => {
      btnIniciarTrabajo.classList.add("oculta");
      if (elSelectorPerfiles) elSelectorPerfiles.classList.remove("oculta");
      fijarReaccion("thinking");
      actualizarBurbuja("¿En qué vas a enfocarte hoy?", [
        ["fotos", "📸 Fotos"],
        ["coding", "💻 Vibe Coding"],
      ]);
    });
  }

  const btnPerfilFotos = $("#btn-perfil-fotos");
  if (btnPerfilFotos) {
    btnPerfilFotos.addEventListener("click", () => iniciarPerfil("fotos"));
  }

  const btnPerfilCoding = $("#btn-perfil-coding");
  if (btnPerfilCoding) {
    btnPerfilCoding.addEventListener("click", () => iniciarPerfil("coding"));
  }

  const btnCerrarSesion = $("#btn-cerrar-sesion");
  if (btnCerrarSesion) {
    btnCerrarSesion.addEventListener("click", () => cerrarSesionTrabajo());
  }

  // Toque a la mascota para saludar
  const shell = $("#pet-shell");
  if (shell) {
    shell.addEventListener("click", () => {
      fijarReaccion("waving");
      actualizarBurbuja("¡Hola! ¿En qué avanzamos?", []);
      api("POST", "/api/phone/wake");
      setTimeout(() => {
        if (reaccionActual === "waving") fijarReaccion("idle");
      }, 3500);
    });
  }

  // Botón Pausa / Dormitar (+5m)
  const btnPausa = $("#btn-pausa-5m");
  if (btnPausa) {
    btnPausa.addEventListener("click", () => {
      accionControl("pause_extend", "⏸ Pausa +5 min aplicada", "thinking");
    });
  }

  // Botón Micrófono
  const btnVoz = $("#btn-voz");
  if (btnVoz) {
    btnVoz.addEventListener("click", () => {
      fijarReaccion("waiting");
      actualizarBurbuja("🎤 Escuchando por el micrófono de la PC... ¡Habla ahora!", []);
      accionControl("start_voice", "🎤 Micrófono PC activado", "waiting");
      api("POST", "/api/phone/wake");
    });
  }

  // Botón Foco (+5m)
  const btnSeguir = $("#btn-seguir-5m");
  if (btnSeguir) {
    btnSeguir.addEventListener("click", () => {
      accionControl("seguir_extend", "▶ Foco +5 min confirmado", "working");
    });
  }
}

/* ---------------- Arranque ------------------ */

document.addEventListener("DOMContentLoaded", () => {
  fijarReaccion("idle");
  inicializarInteracciones();
  actualizarEstadoMascota();
  setInterval(() => {
    if (!document.hidden) {
      actualizarEstadoMascota();
    }
  }, 5000);
});
