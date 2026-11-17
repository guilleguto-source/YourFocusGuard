/* Widget de la Mascota Móvil — Asistente TDAH (v0.12.1)
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
function toast(mensaje, largo = 2600) {
  const el = $("#toast");
  el.textContent = mensaje;
  el.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("visible"), largo);
}

function ahoraTexto() {
  return new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

/* ---------------- Reloj + Estado ------------ */

function actualizarReloj() {
  const el = $("#reloj");
  if (el) el.textContent = ahoraTexto();
}
setInterval(actualizarReloj, 1000);
actualizarReloj();

let estadoOnline = false;
function setOnline(ok) {
  estadoOnline = ok;
  const dot = $("#estado-dot");
  if (dot) {
    dot.style.background = ok ? "var(--ok)" : "var(--peligro)";
    dot.title = ok ? "Conectado al Asistente" : "Buscando servidor...";
  }
}

/* ---------------- Mascota y Diálogo --------- */

let mascotaActual = "einstein";
let reaccionActual = "idle";
let ultimoTextoBurbuja = "";

function normalizarOpcion(op) {
  if (Array.isArray(op)) {
    return String(op[1] || op[0] || "");
  }
  return String(op || "");
}

function actualizarBurbuja(texto, opciones) {
  const burbuja = $("#burbuja");
  const elTexto = $("#burbuja-texto");
  const elOpciones = $("#burbuja-opciones");
  if (!burbuja || !elTexto || !elOpciones) return;

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
  toast(`Enviando: ${normalizarOpcion(op)}...`);
  const r = await api("POST", "/api/pet/responder", { respuesta: clave });
  if (r.ok) {
    actualizarBurbuja("Entendido.", []);
  }
}

async function actualizarEstadoMascota() {
  const r = await api("GET", "/api/pet/state");
  if (r.ok && r.datos) {
    setOnline(true);
    const d = r.datos;

    // Mascota activa
    const m = d.mascota || "einstein";
    if (m !== mascotaActual) {
      mascotaActual = m;
      $("#pet-nombre").textContent = m.charAt(0).toUpperCase() + m.slice(1);
      const img = $("#avatar-img");
      if (img) img.src = `/pets/${m}/spritesheet.webp`;
    }

    // Reacción
    const reacc = d.reaccion || "idle";
    if (reacc !== reaccionActual) {
      reaccionActual = reacc;
      const estadoTxt = {
        idle: "En espera",
        foco: "Concentrado",
        celebrating: "¡Festejando!",
        alert: "Atento a la tarea",
        waiting: "Preguntando...",
      }[reacc] || "Activo";
      $("#pet-estado-texto").textContent = estadoTxt;
    }

    // Burbuja
    const burbuja = d.burbuja || {};
    const txt = burbuja.texto || "";
    const ops = burbuja.opciones || [];
    if (txt !== ultimoTextoBurbuja || ops.length > 0) {
      ultimoTextoBurbuja = txt;
      actualizarBurbuja(txt, ops);
    }
  } else {
    setOnline(false);
  }
}

/* ---------------- Botonera de Acciones ------ */

async function accionControl(cmd, mensajeToast) {
  toast(mensajeToast);
  const r = await api("POST", "/api/control", { cmd });
  if (!r.ok) {
    // Si /api/control no responde en adhd-assistant, intentar endpoint directo
    await api("POST", "/api/pet/control", { cmd });
  }
}

function inicializarBotones() {
  const btnPausa = $("#btn-pausa-5m");
  if (btnPausa) {
    btnPausa.addEventListener("click", () => {
      accionControl("pause_extend", "⏸ Pausa +5 min aplicada");
    });
  }

  const btnVoz = $("#btn-voz");
  if (btnVoz) {
    btnVoz.addEventListener("click", () => {
      accionControl("start_voice", "🎤 Activando escucha por voz...");
    });
  }

  const btnSeguir = $("#btn-seguir-5m");
  if (btnSeguir) {
    btnSeguir.addEventListener("click", () => {
      accionControl("seguir_extend", "▶ Foco +5 min confirmado");
    });
  }
}

/* ---------------- Arranque ------------------ */

document.addEventListener("DOMContentLoaded", () => {
  inicializarBotones();
  actualizarEstadoMascota();
  setInterval(actualizarEstadoMascota, 1500);
});
