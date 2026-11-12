/* ===========================================================================
   YourFocusGuard · Panel del Guardián — comportamiento (vanilla, sin build)
   =========================================================================== */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ------------------------- utilidades ------------------------- */

function fmtSegundos(seg) {
  seg = Math.round(seg);
  if (seg < 60) return `${seg} s`;
  const m = Math.floor(seg / 60);
  const s = seg % 60;
  return s === 0 ? `${m} min` : `${m} min ${s} s`;
}

function fmtMinutos(min) {
  min = Math.round(min);
  return `${min} min`;
}

/** "lightroom, photoshop" -> ["lightroom", "photoshop"] (máx. 8, sin vacíos). */
function leerListaApps(valor) {
  const vistos = new Set();
  const salida = [];
  String(valor || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .forEach((x) => {
      if (x && !vistos.has(x) && salida.length < 8) {
        vistos.add(x);
        salida.push(x);
      }
    });
  return salida;
}

function toast(mensaje, esError = false) {
  const el = $("#toast");
  el.textContent = mensaje;
  el.classList.toggle("toast-error", esError);
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 4200);
}

async function api(ruta, cuerpo) {
  const opciones = cuerpo
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) }
    : {};
  const r = await fetch(ruta, opciones);
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.error || `HTTP ${r.status}`);
  return datos;
}

/* ------------------------- estado global ------------------------- */

let configOriginal = null;   // último snapshot aplicado (para "descartar")
let prohibitioDuplicadas = new Set();
let pollTimer = null;

/* ------------------------- tema claro/oscuro ------------------------- */

function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema;
  $("#boton-tema-texto").textContent = tema === "oscuro" ? "Claro" : "Oscuro";
  try { localStorage.setItem("yfg-tema", tema); } catch (e) { /* modo privado */ }
}

$("#boton-tema").addEventListener("click", () => {
  aplicarTema(document.documentElement.dataset.tema === "oscuro" ? "claro" : "oscuro");
});

/* ------------------------- navegación por pestañas (Tabs) ------------------------- */

function activarTab(tabId) {
  const botones = $$(".tab-boton");
  const paneles = $$(".tab-panel");

  botones.forEach((btn) => {
    const esActivo = btn.dataset.tab === tabId;
    btn.classList.toggle("activo", esActivo);
    btn.setAttribute("aria-selected", esActivo ? "true" : "false");
  });

  paneles.forEach((panel) => {
    if (panel.id === tabId) {
      panel.hidden = false;
      panel.classList.add("activo");
    } else {
      panel.hidden = true;
      panel.classList.remove("activo");
    }
  });

  try {
    sessionStorage.setItem("yfg-tab-activa", tabId);
  } catch (e) {
    /* modo privado */
  }
}

$$(".tab-boton").forEach((btn) => {
  btn.addEventListener("click", () => {
    activarTab(btn.dataset.tab);
  });
});

/* ------------------------- sliders con relleno ------------------------- */

function pintarSlider(input) {
  const min = Number(input.min);
  const max = Number(input.max);
  const pct = ((Number(input.value) - min) / (max - min)) * 100;
  input.style.setProperty("--relleno", `${pct}%`);
}

$$('input[type="range"]').forEach((input) => {
  pintarSlider(input);
  input.addEventListener("input", () => pintarSlider(input));
});

/* ------------------------- sincronizar outputs ------------------------- */

function refrescarOutputs() {
  $("#frecuencia-valor").textContent = fmtSegundos(Number($("#frecuencia").value));
  $("#inactividad-valor").textContent = fmtSegundos(Number($("#inactividad").value));
  $("#r1-valor").textContent = fmtSegundos(Number($("#r1").value));
  $("#r2-valor").textContent = fmtSegundos(Number($("#r2").value));
  const seg = Number($("#frecuencia").value);
  const porHora = Math.round(3600 / seg);
  const fifo = seg * 5;
  const ram = (fifo / seg) * 0.62; // ~0.6 MB por frame reducido (estimación)
  $("#frecuencia-derivado").innerHTML =
    `≈ <strong>${porHora}</strong> capturas/hora · memoria FIFO ` +
    `≈ <strong>${fmtSegundos(fifo)}</strong> · ≈ <strong>${ram.toFixed(1)} MB</strong> en RAM (estimado)`;
}

["#frecuencia", "#inactividad", "#r1", "#r2"].forEach((sel) => {
  $(sel).addEventListener("input", refrescarOutputs);
});

/* ------------------------- modo de aviso ------------------------- */

$$('input[name="modo"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    $("#zona-completo").hidden = !$('input[name="modo"]:checked') || $('input[name="modo"]:checked').value !== "completo";
    marcarSucio();
  });
});

/* ------------------------- opciones colapsables (progressive disclosure) ------------------------- */

function sincronizarColapsables() {
  const flujosActivo = $("#flujos-activo");
  const flujosDetalles = $("#flujos-detalles");
  if (flujosActivo && flujosDetalles) {
    flujosDetalles.classList.toggle("colapsado", !flujosActivo.checked);
  }

  const concActiva = $("#concentracion-activa");
  const concDetalles = $("#concentracion-detalles");
  if (concActiva && concDetalles) {
    concDetalles.classList.toggle("colapsado", !concActiva.checked);
  }

  const presActiva = $("#presencia-activa");
  const presDetalles = $("#presencia-detalles");
  if (presActiva && presDetalles) {
    presDetalles.classList.toggle("colapsado", !presActiva.checked);
  }
}

["#flujos-activo", "#concentracion-activa", "#presencia-activa"].forEach((sel) => {
  const el = $(sel);
  if (el) {
    el.addEventListener("change", sincronizarColapsables);
  }
});

/* ------------------------- sucio / guardar / descartar ------------------------- */

function marcarSucio() {
  $("#barra-guardado").hidden = false;
}

function limpiarSucio() {
  $("#barra-guardado").hidden = true;
}

[
  "#frecuencia", "#inactividad", "#r1", "#r2", "#pantalla", "#pantalla-num",
  "#tras", "#app-objetivo", "#mascota-visible", "#mascota-tema", "#captura-activa",
  "#sesion-apps", "#sesion-aux",
  "#concentracion-activa", "#concentracion-hosts", "#concentracion-audio",
  "#concentracion-dominios", "#concentracion-apps", "#concentracion-duracion",
  "#nivel-1-apagado", "#nivel-2-apagado", "#nivel-3-apagado", "#nivel-5-apagado",
  "#refuerzo-positivo", "#refuerzo-intervalo",
  "#minutos-antes-de-traer",
  "#presencia-activa", "#presencia-intervalo", "#presencia-ausente", "#presencia-telefono",
  "#presencia-indice",
  "#flujos-activo", "#flujos-aprendizaje", "#flujos-umbral",
].forEach((sel) => {
  const el = $(sel);
  if (!el) return;
  el.addEventListener("input", marcarSucio);
  el.addEventListener("change", marcarSucio);
});

$("#descartar").addEventListener("click", () => {
  if (configOriginal) aplicarConfig(configOriginal, true);
  limpiarSucio();
  toast("Cambios descartados.");
});

$("#guardar").addEventListener("click", async () => {
  const boton = $("#guardar");
  boton.disabled = true;
  try {
    if (prohibitioDuplicadas.size) {
      toast("Hay patrones repetidos: corrígelos antes de guardar.", true);
      return;
    }
    const vacias = leerProhibiciones().filter((p) => !p.patron).length;
    if (vacias) {
      toast("Hay prohibiciones sin patrón: complétalas o quítalas.", true);
      return;
    }
    const prohibiciones = leerProhibiciones().map((p) => ({
      patron: p.patron,
      limite_min_dia: p.limite,
      bloqueo_activo: p.bloqueo,
      excepciones: p.excepciones,
    }));
    const cuerpo = {
      captura: {
        habilitada: $("#captura-activa").checked,
        intervalo_seg: Number($("#frecuencia").value),
        monitor: monitorElegido(),
      },
      alertas: {
        desvio_sostenido_seg: Number($("#inactividad").value),
        modo: $('input[name="modo"]:checked').value,
        traer_al_frente_app: $("#app-objetivo").value.trim().toLowerCase(),
        traer_al_frente_tras: Number($("#tras").value),
        minutos_antes_de_traer: Number($("#minutos-antes-de-traer").value || 2),
        nivel_1_apagado: $("#nivel-1-apagado").checked,
        nivel_2_apagado: $("#nivel-2-apagado").checked,
        nivel_3_apagado: $("#nivel-3-apagado").checked,
        nivel_5_apagado: $("#nivel-5-apagado").checked,
        refuerzo_positivo: $("#refuerzo-positivo") ? $("#refuerzo-positivo").checked : true,
        refuerzo_intervalo_min: Number($("#refuerzo-intervalo") ? $("#refuerzo-intervalo").value : 10),
      },
      sesion: {
        segundos_fuera_app: Number($("#r1").value),
        segundos_inactivo: Number($("#r2").value),
        apps: leerListaApps($("#sesion-apps").value),
        apps_auxiliares: leerListaApps($("#sesion-aux").value),
      },
      mascota: {
        visible: $("#mascota-visible").checked,
        tema: $("#mascota-tema").value,
      },
      concentracion: {
        habilitado: $("#concentracion-activa").checked,
        bloquear_hosts: $("#concentracion-hosts").checked,
        silenciar_audio: $("#concentracion-audio").checked,
        dominios: leerListaApps($("#concentracion-dominios").value),
        apps_bloqueadas: leerListaApps($("#concentracion-apps").value),
        duracion_min: Number($("#concentracion-duracion").value || 0),
      },
      presencia: {
        habilitada: $("#presencia-activa").checked,
        indice_camara: Number($("#presencia-indice").value || 0),
        intervalo_seg: Number($("#presencia-intervalo").value || 30),
        ausencia_seg: Number($("#presencia-ausente").value || 120),
        telefono_en_mano_seg: 10,
      },
      flujos: {
        habilitado: $("#flujos-activo") ? $("#flujos-activo").checked : true,
        aprendizaje: $("#flujos-aprendizaje") ? $("#flujos-aprendizaje").checked : true,
        umbral_descubrimiento_min: Number($("#flujos-umbral") ? $("#flujos-umbral").value : 2),
        grupo: leerGruposFlujos(),
      },
      prohibiciones: { lista: prohibiciones || [] },
    };
    const respuesta = await api("/api/config", cuerpo);
    toast(respuesta.nota || "Guardado.");
    limpiarSucio();
    refrescarEstado(); // re-sincroniza el snapshot "original"
  } catch (e) {
    toast(`No se pudo guardar: ${e.message}`, true);
  } finally {
    boton.disabled = false;
  }
});

/* ------------------------- pantalla principal ------------------------- */

function monitorElegido() {
  const zona = $("#pantalla-select-zona");
  if (zona.hidden) return Math.max(1, Math.min(16, Number($("#pantalla-num").value || 1)));
  return Number($("#pantalla").value || 1);
}

function pintarMonitores(monitores, actual) {
  const select = $("#pantalla");
  select.innerHTML = "";
  if (!monitores.length) {
    $("#pantalla-select-zona").hidden = true;
    $("#pantalla-manual").hidden = false;
    $("#pantalla-num").value = actual;
    return;
  }
  $("#pantalla-select-zona").hidden = false;
  $("#pantalla-manual").hidden = true;
  monitores.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.indice;
    opt.textContent =
      `Monitor ${m.indice} · ${m.ancho}×${m.alto}` +
      (m.primaria ? " · principal" : "") +
      (m.indice === actual ? "  (capturando)" : "");
    if (m.indice === actual) opt.selected = true;
    select.appendChild(opt);
  });
}

/* ------------------------- prohibiciones ------------------------- */

function leerProhibiciones() {
  return $$(".prohibicion").map((fila) => ({
    patron: fila.querySelector(".proh-patron").value.trim().toLowerCase(),
    limite: Math.max(5, Math.min(480, Number(fila.querySelector(".proh-limite").value || 60))),
    bloqueo: fila.querySelector(".proh-bloqueo input").checked,
    excepciones: fila.querySelector(".proh-excepciones").value
      .split(",")
      .map((x) => x.trim().toLowerCase())
      .filter(Boolean)
      .slice(0, 8),
    // progreso (solo lectura)
    usadoEl: fila.querySelector(".proh-hoy"),
    barraEl: fila.querySelector(".proh-barra-relleno"),
    filaEl: fila,
  })).filter((p) => p.patron !== "__vacia__");
}

function validarProhibiciones() {
  const filas = $$(".prohibicion");
  prohibitioDuplicadas = new Set();
  const vistos = new Map();
  filas.forEach((fila) => {
    fila.classList.remove("repetida");
    const patron = fila.querySelector(".proh-patron").value.trim().toLowerCase();
    const esVacia = !patron;
    fila.querySelector(".proh-patron").setCustomValidity("");
    if (!esVacia) {
      if (vistos.has(patron)) {
        prohibitioDuplicadas.add(patron);
        vistos.get(patron).classList.add("repetida");
        fila.classList.add("repetida");
        fila.querySelector(".proh-patron").setCustomValidity("Patrón repetido");
      } else {
        vistos.set(patron, fila);
      }
    }
  });
}

function filaProhibicion(patron = "", limite = 60, bloqueo = false, excepciones = []) {
  const div = document.createElement("article");
  div.className = "prohibicion";
  div.innerHTML = `
    <div class="proh-campo">
      <label>App o sitio</label>
      <input type="text" class="proh-patron" maxlength="64" placeholder="youtube · instagram · steam…"
             value="${patron.replace(/"/g, "&quot;")}">
    </div>
    <div class="proh-campo">
      <label>Límite (min/día)</label>
      <input type="number" class="proh-limite" min="5" max="480" step="5" value="${limite}">
    </div>
    <div class="proh-campo">
      <label>Permitido (excepciones)</label>
      <input type="text" class="proh-excepciones" maxlength="200" placeholder="p. ej. youtube music, mix…"
             value="${(excepciones || []).join(", ").replace(/"/g, "&quot;")}">
      <small>títulos que NO cuentan (p. ej. música sí, vídeos no)</small>
    </div>
    <div class="proh-bloqueo">
      <span class="proh-bloqueo-etiqueta">Bloqueo activo</span>
      <label class="interruptor">
        <input type="checkbox" ${bloqueo ? "checked" : ""}>
        <span class="interruptor-pieza"></span>
      </label>
      <small>al agotarse: minimizar</small>
    </div>
    <div class="proh-progreso">
      <div class="proh-barra"><div class="proh-barra-relleno"></div></div>
      <div class="proh-numeros">
        <span class="proh-hoy">hoy 0 min</span>
        <span class="proh-tope">tope —</span>
      </div>
    </div>
    <button type="button" class="proh-quitar" title="Quitar">×</button>`;
  div.querySelector(".proh-quitar").addEventListener("click", () => {
    div.remove();
    refrescarVacio();
    marcarSucio();
    validarProhibiciones();
  });
  div.addEventListener("input", () => {
    marcarSucio();
    validarProhibiciones();
  });
  return div;
}

function refrescarVacio() {
  $("#prohibiciones-vacio").hidden = $$(".prohibicion").length > 0;
}

$("#agregar-prohibicion").addEventListener("click", () => {
  $("#lista-prohibiciones").appendChild(filaProhibicion());
  refrescarVacio();
  marcarSucio();
  $$(".prohibicion .proh-patron").at(-1).focus();
});

$$("#chips-rapidos .chip-boton").forEach((chip) => {
  chip.addEventListener("click", () => {
    const existentes = leerProhibiciones().map((p) => p.patron);
    if (existentes.includes(chip.dataset.patron)) {
      toast("Ya tienes una prohibición con ese patrón.", true);
      return;
    }
    const excepciones = (chip.dataset.excepciones || "")
      .split(",").map((x) => x.trim()).filter(Boolean);
    $("#lista-prohibiciones").appendChild(
      filaProhibicion(chip.dataset.patron, Number(chip.dataset.limite), true, excepciones)
    );
    refrescarVacio();
    marcarSucio();
  });
});

function actualizarProgresos(prohibiciones) {
  const filas = leerProhibiciones();
  filas.forEach((f) => {
    const info = prohibiciones.find((p) => p.patron === f.patron);
    const usado = info ? info.usado_min : 0;
    const limite = info ? info.limite_min : f.limite;
    const excedida = info ? info.excedido : usado >= limite;
    f.usadoEl.textContent = `hoy ${fmtMinutos(usado)}`;
    f.filaEl.querySelector(".proh-tope").textContent = `tope ${limite} min`;
    f.filaEl.querySelector(".proh-limite").value = limite;
    f.filaEl.classList.toggle("excedida", excedida);
    const pct = limite > 0 ? Math.min(100, (usado / limite) * 100) : 0;
    f.barraEl.style.width = `${pct}%`;
  });
}

function renderizarGruposFlujos(grupos) {
  const cont = $("#lista-flujos");
  if (!cont) return;
  cont.innerHTML = "";
  (grupos || []).forEach((g, idx) => {
    const div = document.createElement("div");
    div.className = "subtarjeta";
    div.style.marginTop = "0";
    div.innerHTML = `
      <div style="font-weight: 700; margin-bottom: 6px;">📂 ${g.nombre || "Flujo"}</div>
      <div class="campo" style="margin-bottom: 6px;">
        <label style="font-size: 12px; min-width: 130px;">Apps principales:</label>
        <input type="text" class="flujo-apps" data-idx="${idx}" value="${(g.apps || []).join(', ')}" style="flex: 1;" placeholder="lightroom, photoshop">
      </div>
      <div class="campo" style="margin-bottom: 6px;">
        <label style="font-size: 12px; min-width: 130px;">Apps relacionadas:</label>
        <input type="text" class="flujo-rel" data-idx="${idx}" value="${(g.apps_relacionadas || []).join(', ')}" style="flex: 1;" placeholder="gutoflow, bridge, explorer">
      </div>
      <div class="campo" style="margin-bottom: 6px;">
        <label style="font-size: 12px; min-width: 130px;">Tolerancia (min):</label>
        <input type="number" class="flujo-tol" data-idx="${idx}" value="${g.tolerancia_min || 2}" min="0.5" max="60" step="0.5" style="width: 80px;">
        <span style="font-size: 12px; color: var(--texto-mutado); margin-left: 8px;">antes de alertar</span>
      </div>
    `;
    div.addEventListener("input", marcarSucio);
    div.addEventListener("change", marcarSucio);
    cont.appendChild(div);
  });
}

function leerGruposFlujos() {
  const grupos = [];
  const elementos = $$("#lista-flujos .subtarjeta");
  elementos.forEach((el, idx) => {
    const inputApps = el.querySelector(".flujo-apps");
    const inputRel = el.querySelector(".flujo-rel");
    const inputTol = el.querySelector(".flujo-tol");
    const orig = (configOriginal?.flujos_grupos || [])[idx] || {};
    grupos.push({
      nombre: orig.nombre || (idx === 0 ? "edicion_foto" : "desarrollo"),
      apps: leerListaApps(inputApps ? inputApps.value : ""),
      apps_relacionadas: leerListaApps(inputRel ? inputRel.value : ""),
      tolerancia_min: Number(inputTol ? inputTol.value : 2),
      mensaje_aviso: orig.mensaje_aviso || "",
    });
  });
  return grupos;
}

/* ------------------------- aplicar config del servidor ------------------------- */

function aplicarConfig(cfg, esDescarte = false) {
  const hayEdiciones = !esDescarte && !$("#barra-guardado").hidden;
  if (hayEdiciones) {
    return; // no pisar lo que la usuaria está editando
  }
  configOriginal = cfg;
  $("#frecuencia").value = cfg.captura_intervalo_seg;
  $("#captura-activa").checked = cfg.captura_habilitada === true;
  $("#inactividad").value = cfg.desvio_sostenido_seg;
  $("#r1").value = cfg.sesion_fuera_app;
  $("#r2").value = cfg.sesion_inactivo;
  $("#sesion-apps").value = (cfg.sesion_apps || []).join(", ");
  $("#sesion-aux").value = (cfg.sesion_aux || []).join(", ");
  pintarSlider($("#frecuencia"));
  pintarSlider($("#inactividad"));
  pintarSlider($("#r1"));
  pintarSlider($("#r2"));

  // modo de aviso
  const modo = cfg.modo || "visual_sonoro";
  $$('input[name="modo"]').forEach((r) => { r.checked = r.value === modo; });
  $("#zona-completo").hidden = modo !== "completo";
  $("#tras").value = String(cfg.traer_al_frente_tras || 2);
  $("#app-objetivo").value = cfg.traer_al_frente_app || "";
  $("#minutos-antes-de-traer").value = cfg.minutos_antes_de_traer || 2;
  $("#nivel-1-apagado").checked = cfg.nivel_1_apagado === true;
  $("#nivel-2-apagado").checked = cfg.nivel_2_apagado === true;
  $("#nivel-3-apagado").checked = cfg.nivel_3_apagado === true;
  $("#nivel-5-apagado").checked = cfg.nivel_5_apagado === true;
  if ($("#refuerzo-positivo")) {
    $("#refuerzo-positivo").checked = cfg.refuerzo_positivo !== false;
  }
  if ($("#refuerzo-intervalo")) {
    $("#refuerzo-intervalo").value = cfg.refuerzo_intervalo_min || 10;
  }

  // mascota
  const selectTema = $("#mascota-tema");
  selectTema.innerHTML = "";
  (cfg.temas || ["clasico"]).forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = { clasico: "Clásico (greige)", oscuro: "Oscuro", calido: "Cálido (beige)" }[t] || t;
    if (t === cfg.mascota_tema) opt.selected = true;
    selectTema.appendChild(opt);
  });
  $("#mascota-visible").checked = cfg.mascota_visible !== false;

  // concentración
  $("#concentracion-activa").checked = cfg.concentracion_habilitada === true;
  $("#concentracion-hosts").checked = cfg.concentracion_bloquear_hosts !== false;
  $("#concentracion-audio").checked = cfg.concentracion_silenciar_audio !== false;
  $("#concentracion-dominios").value = (cfg.concentracion_dominios || []).join(", ");
  $("#concentracion-apps").value = (cfg.concentracion_apps_bloqueadas || []).join(", ");
  $("#concentracion-duracion").value = cfg.concentracion_duracion_min || 0;

  // presencia
  $("#presencia-activa").checked = cfg.presencia_habilitada === true;
  $("#presencia-indice").value = cfg.presencia_indice_camara || 0;
  $("#presencia-intervalo").value = cfg.presencia_intervalo_seg || 30;
  $("#presencia-ausente").value = cfg.presencia_ausente_para_pausar_seg || 120;
  $("#presencia-telefono").checked = true;

  // flujos
  if ($("#flujos-activo")) {
    $("#flujos-activo").checked = cfg.flujos_habilitado !== false;
    $("#flujos-aprendizaje").checked = cfg.flujos_aprendizaje !== false;
    $("#flujos-umbral").value = cfg.flujos_umbral_descubrimiento_min || 2;
    renderizarGruposFlujos(cfg.flujos_grupos || []);
  }

  // prohibiciones: reconstruir desde el servidor
  $("#lista-prohibiciones").innerHTML = "";
  (cfg.__prohibiciones || []).forEach((p) => {
    $("#lista-prohibiciones").appendChild(
      filaProhibicion(p.patron, p.limite_min, p.bloqueo_activo, p.excepciones || [])
    );
  });
  refrescarVacio();
  refrescarOutputs();
  sincronizarColapsables();
}

/* ------------------------- estado en vivo ------------------------- */

const CLASES_ESTADO = {
  FOCO: ["chip-verde", "corriendo"],
  EN_ESPERA: ["chip-neutro", "calentando"],
  PAUSA: ["chip-amarilla", "en pausa"],
  ESCALADA: ["chip-roja", "desvío"],
  COOLDOWN: ["chip-amarilla", "enfriando"],
};

async function refrescarEstado() {
  try {
    const datos = await api("/api/estado");
    const cfg = datos.config;
    cfg.__prohibiciones = datos.prohibiciones;
    aplicarConfig(cfg);
    actualizarProgresos(datos.prohibiciones || []);

    // chip de la cabecera
    const chip = $("#chip-estado");
    const est = datos.corriendo ? (datos.estado?.estado || "—") : "detenido";
    chip.className = "chip " + (CLASES_ESTADO[est]?.[0] || "chip-neutro");
    chip.textContent = datos.corriendo
      ? `${est.toLowerCase()} · ${(CLASES_ESTADO[est]?.[1] || "activo")}`
      : "agente detenido";

    // hero
    const st = datos.estado || {};
    $("#st-estado").textContent = datos.corriendo ? (st.estado || "—") : "detenido";
    $("#st-estado").className = "";
    if (datos.corriendo && st.estado === "ESCALADA") $("#st-estado").classList.add("roja");
    if (datos.corriendo && st.estado === "FOCO") $("#st-estado").classList.add("verde");
    $("#st-estado-detalle").textContent = datos.corriendo
      ? (st.tarea ? `tarea: ${st.tarea}` : (st.cerebro || "sin tarea"))
      : "el conteo de prohibiciones corre solo con el agente activo";

    const ses = (st.sesion) || {};
    $("#st-sesion").textContent = ses.activa ? "en tarea" : "sin sesión";
    $("#st-sesion-detalle").textContent = ses.activa
      ? `${(st.tarea || "sesión")}${st.sesion?.disparos ? ` · ${st.sesion.disparos} avisos` : ""}`
      : "declárala con: python run.py session start";

    // tarjeta "Sesión de hoy" (v0.5.0)
    if (ses.activa) {
      const apps = (ses.apps || []).join(", ") || "solo inactividad";
      const fuera = ses.fuera_hace_s;
      $("#sesion-estado").textContent =
        `Sesión activa · ${apps} · ${ses.disparos || 0} avisos` +
        (fuera !== null && fuera !== undefined ? ` · en la tarea hace ${fuera} s` : "");
    } else {
      $("#sesion-estado").textContent = "sin sesión declarada";
    }
    if (st.tarea && document.activeElement !== $("#sesion-tarea")) {
      $("#sesion-tarea").value = st.tarea;
    }

    // cara activa (v0.6.0): OpenPets, mascota integrada o ninguna
    const avatar = (st.avisos || {}).avatar;
    const nombreAvatar = { openpets: "OpenPets", tk: "mascota integrada" }[avatar]
      || "ninguna (consola y toasts)";
    $("#avatar-estado").textContent = `Cara activa: ${nombreAvatar}`;

    // estado de concentración y presencia (v0.7.0)
    const conc = (st.concentracion || {});
    const pres = (st.presencia || {});
    let concTexto = "concentración: —";
    if (conc.activo) {
      const mins = Math.floor((conc.duracion_seg || 0) / 60);
      concTexto = `concentración: ACTIVA · ${mins} min transcurridos · ${conc.dominios.length} dominios`;
    }
    let presTexto = "presencia: —";
    if (pres.disponible) {
      presTexto = `presencia: ${pres.en_silla ? "en silla" : "ausente"}` +
        (pres.telefono_en_mano ? " · teléfono" : "");
    }
    $("#avatar-estado").textContent += ` · ${concTexto} · ${presTexto}`;

    $("#st-nube").textContent = `${datos.nube_usd_hoy.toFixed(3)} USD`;
    $("#st-nube-detalle").textContent = `presupuesto diario ${cfg.presupuesto_diario_usd} USD`;

    $("#pie-version").textContent = `YourFocusGuard v${datos.version}`;
    pintarMonitores(datos.monitores || [], cfg.monitor);
    refrescarOutputs();
  } catch (e) {
    $("#chip-estado").textContent = "sin conexión";
    $("#chip-estado").className = "chip chip-roja";
  }
}

/* ------------------------- botones de control ------------------------- */

$$("#acciones .boton").forEach((boton) => {
  boton.addEventListener("click", async () => {
    const cmd = boton.dataset.cmd;
    try {
      if (cmd === "test_alert") {
        toast("Avisos enviados: mira el toast, escucha el sonido y la voz. La mascota reacciona.");
      } else if (cmd === "pause") {
        toast("Pausa de 15 min enviada al agente.");
      } else if (cmd === "stop") {
        toast("Orden de detención enviada (cierra en el próximo ciclo).");
      } else if (cmd === "resume") {
        toast("Reanudación enviada.");
      }
      await api("/api/control", { cmd });
    } catch (e) {
      toast(`No se pudo enviar: ${e.message}`, true);
    }
  });
});

/* ------------------------- sesión de hoy ------------------------- */

function resumenApps(apps) {
  return apps.length ? apps.join(", ") : "solo inactividad";
}

$("#sesion-iniciar").addEventListener("click", async () => {
  const boton = $("#sesion-iniciar");
  const apps = leerListaApps($("#sesion-apps").value);
  const aux = leerListaApps($("#sesion-aux").value);
  const texto = $("#sesion-tarea").value.trim();
  boton.disabled = true;
  try {
    await api("/api/control", {
      cmd: "session_start",
      texto: texto || "sesión",
      apps,
      aux,
      minutos: 0,
    });
    toast(`Sesión iniciada · ${resumenApps(apps)}`);
    setTimeout(refrescarEstado, 1200);
  } catch (e) {
    toast(`No se pudo iniciar: ${e.message}`, true);
  } finally {
    boton.disabled = false;
  }
});

$("#sesion-cerrar").addEventListener("click", async () => {
  const boton = $("#sesion-cerrar");
  boton.disabled = true;
  try {
    await api("/api/control", { cmd: "session_stop" });
    toast("Sesión cerrada. Buen trabajo.");
    setTimeout(refrescarEstado, 1200);
  } catch (e) {
    toast(`No se pudo cerrar: ${e.message}`, true);
  } finally {
    boton.disabled = false;
  }
});

$("#sesion-detectar").addEventListener("click", async () => {
  const boton = $("#sesion-detectar");
  const original = boton.textContent;
  boton.disabled = true;
  boton.textContent = "Detectando…";
  toast("Cambia ahora a tu programa de trabajo: 10 s de muestreo.");
  try {
    const datos = await api("/api/detectar", { segundos: 10 });
    const apps = datos.apps || [];
    if (apps.length) {
      $("#sesion-apps").value = apps.join(", ");
      marcarSucio();
      toast(`Detectadas: ${apps.join(", ")}`);
    } else {
      toast("No se detectó ninguna app: escríbela a mano.", true);
    }
  } catch (e) {
    toast(`No se pudo detectar: ${e.message}`, true);
  } finally {
    boton.disabled = false;
    boton.textContent = original;
  }
});

/* ------------------------- reporte semanal F5 ------------------------- */

async function refrescarReporteSemanal() {
  try {
    const res = await api("/api/reporte/semanal");
    if (!res.ok || !res.reporte) return;
    const rep = res.reporte;
    const elFoco = $("#rep-foco-total");
    if (elFoco) elFoco.textContent = fmtMinutos(rep.minutos_foco_total || 0);
    const elDesv = $("#rep-desvios-total");
    if (elDesv) elDesv.textContent = String(rep.total_desvios || 0);
    const elPom = $("#rep-pomodoros-total");
    if (elPom) elPom.textContent = String(rep.pomodoros_completados || 0);
    const coste = Number(rep.coste_api_semanal || 0).toFixed(4);
    const segVoz = Math.round(Number(rep.segundos_voz_semanal || 0));
    const elVoz = $("#rep-voz-total");
    if (elVoz) elVoz.textContent = `${segVoz} s`;
    const elVozDet = $("#rep-voz-detalle");
    if (elVozDet) elVozDet.textContent = `coste acumulado: $${coste}`;

    const listaApps = $("#rep-top-apps");
    if (listaApps) {
      if (rep.top_apps_distraccion && rep.top_apps_distraccion.length > 0) {
        listaApps.innerHTML = rep.top_apps_distraccion
          .map(([app, cant]) => `<li><strong>${app}</strong>: ${cant} salidas</li>`)
          .join("");
      } else {
        listaApps.innerHTML = "<li>Sin salidas registradas (¡gran enfoque!)</li>";
      }
    }
  } catch (e) {
    console.debug("No se pudo cargar reporte semanal:", e);
  }
}

const btnRep = $("#btn-refrescar-reporte");
if (btnRep) {
  btnRep.addEventListener("click", () => {
    refrescarReporteSemanal();
    toast("Reporte semanal actualizado.");
  });
}

/* ------------------------- arranque ------------------------- */

try {
  aplicarTema(localStorage.getItem("yfg-tema") || "claro");
} catch (e) {
  aplicarTema("claro");
}

try {
  const guardada = sessionStorage.getItem("yfg-tab-activa");
  if (guardada && $(`#${guardada}`)) {
    activarTab(guardada);
  }
} catch (e) {
  /* noop */
}

refrescarEstado();
refrescarReporteSemanal();
pollTimer = setInterval(refrescarEstado, 5000);
