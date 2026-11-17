/* Widget del celular — Asistente TDAH (v0.12.1)
   Panel táctil estilo PhoneBox: briefing, alarmas, tareas y notas rápidas.
   El token emparejado viaja en cookie (la fija /widget); aquí no se maneja. */
"use strict";

const $ = (sel) => document.querySelector(sel);

/* ---------------- Utilidades ---------------- */

const tokenUrl = new URLSearchParams(window.location.search).get("t") || "";

async function api(metodo, ruta, cuerpo) {
  const opciones = { method: metodo, headers: {} };
  if (tokenUrl) {
    if (!ruta.includes("?")) {
      ruta += "?t=" + encodeURIComponent(tokenUrl);
    } else if (!ruta.includes("t=")) {
      ruta += "&t=" + encodeURIComponent(tokenUrl);
    }
  }
  if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  try {
    const resp = await fetch(ruta, opciones);
    const datos = await resp.json().catch(() => ({}));
    return { ok: resp.ok, estado: resp.status, datos };
  } catch (e) {
    return { ok: false, estado: 0, err: e.message || String(e), datos: {} };
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

/* ---------------- Reloj + estado ---------------- */

function tickReloj() {
  $("#reloj").textContent = ahoraTexto();
  $("#fecha-hoy").textContent = new Date().toLocaleDateString("es", {
    weekday: "long", day: "numeric", month: "long",
  });
}

async function verificarEstado() {
  const { ok } = await api("GET", "/api/salud");
  $("#estado-dot").classList.toggle("ok", ok);
}

/* ---------------- Briefing ---------------- */

async function cargarBriefing() {
  const caja = $("#briefing");
  caja.textContent = "Calculando...";
  const res = await api("GET", "/api/briefing");
  if (!res.ok) {
    caja.textContent = "Error " + res.estado + ": " + (res.err || JSON.stringify(res.datos));
    return;
  }
  caja.textContent = res.datos && res.datos.texto ? res.datos.texto : "Sin texto";
}

/* ---------------- Alarmas ---------------- */

const ALARMA_RAPIDA_LABEL = "Recordatorio rápido";

async function crearAlarma(minutos, label) {
  const { ok, datos } = await api("POST", "/api/timers", { minutos, label });
  toast(ok ? datos.message || "Alarma programada" : datos.message || "No pude programar la alarma");
  if (ok) cargarAlarmas();
}

async function cargarAlarmas() {
  const { ok, datos } = await api("GET", "/api/timers");
  const caja = $("#lista-alarmas");
  if (!ok || !Array.isArray(datos) || datos.length === 0) {
    caja.innerHTML = '<div class="vacio">Sin alarmas activas</div>';
    return;
  }
  caja.innerHTML = "";
  for (const t of datos) {
    const fila = document.createElement("div");
    fila.className = "item";
    const texto = document.createElement("div");
    texto.className = "texto";
    texto.innerHTML = `<div>${escapar(t.label)}</div><div class="detalle">Suena a las ${escapar(t.target_time || "")}</div>`;
    const btn = document.createElement("button");
    btn.className = "btn-item cancelar";
    btn.textContent = "✕";
    btn.setAttribute("aria-label", "Cancelar alarma");
    btn.addEventListener("click", async () => {
      const r = await api("DELETE", `/api/timers/${t.id}`);
      toast(r.ok ? "Alarma cancelada" : "No pude cancelarla");
      cargarAlarmas();
    });
    fila.append(texto, btn);
    caja.appendChild(fila);
  }
}

/* ---------------- Tareas ---------------- */

const PRIORIDAD_ETIQUETA = { 1: "Urgente", 2: "Alta", 3: "Normal", 4: "Baja", 5: "Baja" };

async function cargarTareas() {
  const { ok, datos } = await api("GET", "/api/tasks");
  const caja = $("#lista-tareas");
  if (!ok || !Array.isArray(datos)) {
    caja.innerHTML = '<div class="vacio">No pude leer las tareas</div>';
    return;
  }
  const pendientes = datos.filter((t) => !t.done);
  if (pendientes.length === 0) {
    caja.innerHTML = '<div class="vacio">¡Todo listo, no hay pendientes!</div>';
    return;
  }
  caja.innerHTML = "";
  for (const t of pendientes.slice(0, 12)) {
    const fila = document.createElement("div");
    fila.className = "item";
    const badge = document.createElement("span");
    badge.className = `badge p${t.priority || 3}`;
    badge.textContent = PRIORIDAD_ETIQUETA[t.priority] || "Normal";
    const texto = document.createElement("div");
    texto.className = "texto";
    texto.textContent = t.title;
    const btn = document.createElement("button");
    btn.className = "btn-item hecho";
    btn.textContent = "✓";
    btn.setAttribute("aria-label", "Marcar hecha");
    btn.addEventListener("click", async () => {
      const r = await api("POST", "/api/tasks/complete", { query: t.title });
      toast(r.ok ? `Hecha: ${t.title}` : "No pude completarla");
      cargarTareas();
      cargarBriefing();
    });
    fila.append(badge, texto, btn);
    caja.appendChild(fila);
  }
}

async function agregarTarea() {
  const input = $("#tarea-nueva");
  const titulo = input.value.trim();
  if (!titulo) { toast("Escribe primero la tarea"); return; }
  const prioridad = parseInt($("#tarea-prioridad").value, 10) || 3;
  const { ok, datos } = await api("POST", "/api/tasks", { title: titulo, priority: prioridad });
  toast(ok ? datos.message || "Tarea agregada" : datos.message || "No pude agregarla");
  if (ok) { input.value = ""; cargarTareas(); cargarBriefing(); }
}

/* ---------------- Notas ---------------- */

async function guardarNota() {
  const caja = $("#nota-texto");
  const texto = caja.value.trim();
  if (!texto) { toast("La nota está vacía"); return; }
  const { ok, datos } = await api("POST", "/api/notas", { texto });
  toast(ok ? datos.message || "Nota guardada" : "No pude guardar la nota");
  if (ok) caja.value = "";
}

/* ---------------- Anuncios de alarma (voz + vibración) ---------------- */

async function revisarAnuncios() {
  const { ok, datos } = await api("GET", "/api/timers/announce");
  if (!ok || !Array.isArray(datos) || datos.length === 0) return;
  for (const alarma of datos) {
    const mensaje = alarma.mensaje_hablado || `¡Se acabó el tiempo! ${alarma.label || ""}`;
    toast(mensaje, 6000);
    if (navigator.vibrate) navigator.vibrate([300, 120, 300]);
    try {
      if ("speechSynthesis" in window) {
        const voz = new SpeechSynthesisUtterance(mensaje);
        voz.lang = "es-ES";
        speechSynthesis.speak(voz);
      }
    } catch (e) { /* sin voz: igual vibró */ }
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gan = ctx.createGain();
      osc.connect(gan); gan.connect(ctx.destination);
      osc.frequency.value = 880;
      gan.gain.setValueAtTime(0.25, ctx.currentTime);
      gan.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
      osc.start(); osc.stop(ctx.currentTime + 0.6);
    } catch (e) { /* sin audio */ }
  }
}

/* ---------------- Seguridad XSS mínima ---------------- */

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = String(texto == null ? "" : texto);
  return div.innerHTML;
}

/* ---------------- Arranque y ciclos ---------------- */

function enlazar() {
  $("#btn-briefing").addEventListener("click", cargarBriefing);
  $("#btn-tareas").addEventListener("click", cargarTareas);
  $("#btn-nota").addEventListener("click", guardarNota);
  $("#btn-tarea").addEventListener("click", agregarTarea);
  $("#btn-alarma").addEventListener("click", () => {
    const minutos = parseInt($("#min-custom").value, 10) || 0;
    const label = $("#label-custom").value.trim() || "Recordatorio";
    if (minutos < 1) { toast("Pon los minutos (1-1440)"); return; }
    crearAlarma(minutos, label);
    $("#min-custom").value = "";
    $("#label-custom").value = "";
  });
  document.querySelectorAll(".btn-atalajo").forEach((btn) => {
    btn.addEventListener("click", () => {
      crearAlarma(parseInt(btn.dataset.min, 10), ALARMA_RAPIDA_LABEL);
    });
  });
}

tickReloj();
setInterval(tickReloj, 15000);
setInterval(verificarEstado, 20000);
setInterval(revisarAnuncios, 6000);
setInterval(cargarAlarmas, 20000);
setInterval(cargarTareas, 45000);

verificarEstado();
cargarBriefing();
cargarAlarmas();
cargarTareas();
enlazar();
