// ==============================================================================
// FocusGuard ADHD Assistant - Frontend Engine
// v0.12: memoria de notas + briefing diario hablado + estado del sistema
//        + sync bidireccional con Google Calendar + voz neuronal por trozos
// ==============================================================================

const btnMic = document.getElementById('btnMic');
const statusIndicator = document.getElementById('statusIndicator');
const waveformCanvas = document.getElementById('waveformCanvas');
const canvasCtx = waveformCanvas.getContext('2d');
const textForm = document.getElementById('textForm');
const userInput = document.getElementById('userInput');
const taskList = document.getElementById('taskList');
const btnAddTask = document.getElementById('btnAddTask');
const newTaskInput = document.getElementById('newTaskInput');
const newTaskPriority = document.getElementById('newTaskPriority');
const btnRefreshTasks = document.getElementById('btnRefreshTasks');
const btnSyncCal = document.getElementById('btnSyncCal');
const youtubeForm = document.getElementById('youtubeForm');
const ytQuery = document.getElementById('ytQuery');
const playerTitle = document.getElementById('playerTitle');
const playerBadge = document.getElementById('playerBadge');
const btnStopAudio = document.getElementById('btnStopAudio');
const volumeSlider = document.getElementById('volumeSlider');
const audioStream = document.getElementById('audioStream');
const timersList = document.getElementById('timersList');
const toastContainer = document.getElementById('toastContainer');

// v0.11: Memoria / Notas
const notaInput = document.getElementById('notaInput');
const btnGuardarNota = document.getElementById('btnGuardarNota');
const notaBuscarInput = document.getElementById('notaBuscarInput');
const notasList = document.getElementById('notasList');
const btnRefreshNotas = document.getElementById('btnRefreshNotas');

// v0.11: Briefing
const btnBriefing = document.getElementById('btnBriefing');
const briefingModal = document.getElementById('briefingModal');
const briefingTexto = document.getElementById('briefingTexto');
const btnCerrarBriefing = document.getElementById('btnCerrarBriefing');
const btnCerrarBriefing2 = document.getElementById('btnCerrarBriefing2');
const btnEscucharBriefing = document.getElementById('btnEscucharBriefing');

// v0.12: Salud del sistema
const saludList = document.getElementById('saludList');
const saludUptime = document.getElementById('saludUptime');
const btnSaludTop = document.getElementById('btnSaludTop');
const versionTag = document.getElementById('versionTag');

// --- Global Audio & Recording State ---
let isRecording = false;
let audioContext = null;
let mediaStream = null;
let analyser = null;
let animationFrameId = null;
let recognition = null;
let recordStartTime = 0;
let timerInterval = null;
let ultimoBriefing = '';

// Brown / White Noise Web Audio Node
let noiseNode = null;
let noiseGainNode = null;
let activeNoiseType = null;

// --- Initialize App ---
document.addEventListener('DOMContentLoaded', () => {
  setupRippleEffects();
  initSpeechRecognition();
  loadTasks();
  loadTimers();
  loadNotas();
  loadSalud();
  setupNoisePresets();
  drawIdleWave();
  // Vigilancia de alarmas vencidas (anuncio con voz + beep cada 5s)
  setInterval(checkFinishedTimers, 5000);
  // Refrescar diagnóstico del sistema cada 60s
  setInterval(loadSalud, 60000);
});

// --- Tactile Ripple Effects ---
function setupRippleEffects() {
  document.querySelectorAll('.ripple-btn').forEach(button => {
    button.addEventListener('click', function (e) {
      const circle = document.createElement('span');
      const diameter = Math.max(this.clientWidth, this.clientHeight);
      const radius = diameter / 2;

      const rect = this.getBoundingClientRect();
      circle.style.width = circle.style.height = `${diameter}px`;
      circle.style.left = `${e.clientX - rect.left - radius}px`;
      circle.style.top = `${e.clientY - rect.top - radius}px`;
      circle.classList.add('ripple');

      const ripple = this.querySelector('.ripple');
      if (ripple) ripple.remove();

      this.appendChild(circle);
    });
  });
}

// --- Speech Recognition & Audio Waveform Visualizer ---
function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'es-ES';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map(result => result[0].transcript)
        .join('');
      userInput.value = transcript;
    };

    recognition.onend = () => {
      if (isRecording) {
        stopRecording();
        if (userInput.value.trim()) {
          processMessage(userInput.value.trim());
          userInput.value = '';
        }
      }
    };

    recognition.onerror = (event) => {
      console.warn('Speech recognition error:', event.error);
      showToast('No te escuché bien. Intenta de nuevo o escribe tu orden.', 'error');
      stopRecording();
    };
  }

  // Click / Push-to-Talk on Mic Button
  btnMic.addEventListener('mousedown', startRecording);
  btnMic.addEventListener('mouseup', () => {
    if (isRecording) {
      stopRecording();
      if (userInput.value.trim()) {
        processMessage(userInput.value.trim());
        userInput.value = '';
      }
    }
  });

  // Mobile Touch Support
  btnMic.addEventListener('touchstart', (e) => { e.preventDefault(); startRecording(); });
  btnMic.addEventListener('touchend', (e) => {
    e.preventDefault();
    if (isRecording) {
      stopRecording();
      if (userInput.value.trim()) {
        processMessage(userInput.value.trim());
        userInput.value = '';
      }
    }
  });
}

async function startRecording() {
  if (isRecording) return;
  isRecording = true;
  btnMic.classList.add('recording');
  statusIndicator.className = 'status-indicator listening';
  statusIndicator.textContent = '🎙️ Escuchando... Habla ahora';

  recordStartTime = Date.now();
  timerInterval = setInterval(() => {
    const elapsed = ((Date.now() - recordStartTime) / 1000).toFixed(1);
    statusIndicator.textContent = `🎙️ Escuchando tu voz... (${elapsed}s)`;
  }, 100);

  // Iniciar reconocimiento por voz si está soportado
  if (recognition) {
    try { recognition.start(); } catch (e) {}
  }

  // Activar Analizador Web Audio para la onda visual
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
    if (audioContext.state === 'suspended') await audioContext.resume();

    const source = audioContext.createMediaStreamSource(mediaStream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    drawLiveWave();
  } catch (err) {
    console.warn('No se pudo acceder al micrófono para el visualizador:', err);
    drawSimulatedWave();
  }
}

function stopRecording() {
  if (!isRecording) return;
  isRecording = false;
  btnMic.classList.remove('recording');
  clearInterval(timerInterval);

  statusIndicator.className = 'status-indicator processing';
  statusIndicator.textContent = '⏳ Pensando y organizando tu orden...';

  if (recognition) {
    try { recognition.stop(); } catch (e) {}
  }

  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }

  if (animationFrameId) cancelAnimationFrame(animationFrameId);
  drawIdleWave();
}

// Waveform Drawing
function drawLiveWave() {
  if (!isRecording || !analyser) return;
  const bufferLength = analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);
  analyser.getByteTimeDomainData(dataArray);
  canvasCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
  canvasCtx.lineWidth = 2.5;
  canvasCtx.strokeStyle = '#f43f5e';
  canvasCtx.beginPath();

  const sliceWidth = waveformCanvas.width / bufferLength;
  let x = 0;

  for (let i = 0; i < bufferLength; i++) {
    const v = dataArray[i] / 128.0;
    const y = (v * waveformCanvas.height) / 2;
    if (i === 0) canvasCtx.moveTo(x, y);
    else canvasCtx.lineTo(x, y);
    x += sliceWidth;
  }

  canvasCtx.lineTo(waveformCanvas.width, waveformCanvas.height / 2);
  canvasCtx.stroke();
  animationFrameId = requestAnimationFrame(drawLiveWave);
}

function drawSimulatedWave() {
  if (!isRecording) return;
  canvasCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
  canvasCtx.lineWidth = 2;
  canvasCtx.strokeStyle = '#f43f5e';
  canvasCtx.beginPath();

  const width = waveformCanvas.width;
  const height = waveformCanvas.height;
  const t = Date.now() / 150;

  for (let x = 0; x < width; x += 3) {
    const y = height / 2 + Math.sin(x * 0.05 + t) * Math.sin(x * 0.02) * (height / 2.5);
    if (x === 0) canvasCtx.moveTo(x, y);
    else canvasCtx.lineTo(x, y);
  }
  canvasCtx.stroke();
  animationFrameId = requestAnimationFrame(drawSimulatedWave);
}

function drawIdleWave() {
  canvasCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
  canvasCtx.lineWidth = 1.5;
  canvasCtx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
  canvasCtx.beginPath();
  canvasCtx.moveTo(0, waveformCanvas.height / 2);
  canvasCtx.lineTo(waveformCanvas.width, waveformCanvas.height / 2);
  canvasCtx.stroke();
}

// --- Process Assistant Commands ---
textForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = userInput.value.trim();
  if (!text) return;
  userInput.value = '';
  processMessage(text);
});

async function processMessage(text) {
  statusIndicator.className = 'status-indicator processing';
  statusIndicator.textContent = `⏳ Procesando: "${text}"...`;

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    const data = await resp.json();

    statusIndicator.className = 'status-indicator success';
    statusIndicator.textContent = `✅ ${data.message || 'Acción completada'}`;
    showToast(data.message || 'Comando ejecutado con éxito');

    // Reproducir respuesta por voz neuronal (edge-tts en el servidor)
    speakResponse(data.message);

    // Actualizar secciones según la acción
    if (data.action && data.action.startsWith('tarea')) loadTasks();
    if (data.action === 'crear_alarma') loadTimers();
    if (data.action === 'nota_crear' || data.action === 'nota_buscar') loadNotas();
    if (data.action === 'briefing_diario') {
      mostrarBriefing(data.message || '');
      ultimoBriefing = data.message || '';
    }
    if (data.action === 'audio_youtube') handleYoutubePlayback(data);
    if (data.action === 'audio_noise') startNoise(data.noise_type);
    if (data.action === 'audio_stop') stopAllAudio();

  } catch (err) {
    statusIndicator.className = 'status-indicator';
    statusIndicator.textContent = '⚠️ Error conectando con el asistente.';
    showToast('Error procesando comando', 'error');
  }
}

// --- Voz neuronal (edge-tts vía servidor) con fallback al navegador ---
// v0.12: divide textos largos (briefing) en trozos de ~450 caracteres y
// los reproduce en orden, para no pasarse del límite del endpoint.
async function speakResponse(text) {
  if (!text) return;

  const trozos = dividirTexto(text, 450);

  for (const trozo of trozos) {
    const ok = await hablarTrozo(trozo);
    if (ok) continue;
    // Fallback: la voz del navegador (menos natural, pero siempre funciona)
    return hablarNavegador(trozos.join(' '));
  }
}

async function hablarTrozo(texto) {
  try {
    const resp = await fetch('/api/tts?text=' + encodeURIComponent(texto));
    if (!resp.ok) return false;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    return await new Promise((resolve) => {
      const audio = new Audio(url);
      audio.onended = () => { URL.revokeObjectURL(url); resolve(true); };
      audio.onerror = () => { URL.revokeObjectURL(url); resolve(false); };
      audio.play().catch(() => resolve(false));
    });
  } catch (e) {
    return false;
  }
}

function hablarNavegador(text) {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'es-ES';
    utterance.rate = 1.05;
    window.speechSynthesis.speak(utterance);
    return true;
  }
  return false;
}

function dividirTexto(texto, maxLen) {
  if (!texto) return [];
  if (texto.length <= maxLen) return [texto];

  // Cortar por frases (., !, ?) sin pasarse del máximo
  const frases = texto.match(/[^.!?]+[.!?]*/g) || [texto];
  const trozos = [];
  let actual = '';
  for (const f of frases) {
    if ((actual + f).length > maxLen && actual) {
      trozos.push(actual.trim());
      actual = '';
    }
    actual += f;
  }
  if (actual.trim()) trozos.push(actual.trim());
  return trozos.length ? trozos : [texto];
}

// --- Alarmas: vigilancia y anuncio audible aunque la consola esté cerrada ---
async function checkFinishedTimers() {
  try {
    const resp = await fetch('/api/timers/announce');
    if (!resp.ok) return;
    const vencidas = await resp.json();
    for (const t of vencidas) {
      showToast(`⏰ ¡Alarma! ${t.label}`);
      playAlarmBeep();
      // v0.10: el servidor manda el mensaje con fecha completa listo para hablar
      speakResponse(t.mensaje_hablado || `¡Se acabó el tiempo! ${t.label}`);
      loadTimers();
    }
  } catch (e) { /* servidor no disponible */ }
}

function playAlarmBeep() {
  try {
    if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
    if (audioContext.state === 'suspended') audioContext.resume();

    [0, 350, 700].forEach(delay => {
      setTimeout(() => {
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();
        osc.connect(gain);
        gain.connect(audioContext.destination);
        osc.type = 'sine';
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.001, audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.4, audioContext.currentTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.3);
        osc.start();
        osc.stop(audioContext.currentTime + 0.32);
      }, delay);
    });
  } catch (e) {}
}

// --- Tasks Management (Dual Sync) ---
async function loadTasks() {
  try {
    const resp = await fetch('/api/tasks');
    const tasks = await resp.json();
    renderTasks(tasks);
  } catch (e) {
    taskList.innerHTML = '<li class="empty-state">No se pudieron cargar las tareas.</li>';
  }
}

function renderTasks(tasks) {
  if (!tasks || tasks.length === 0) {
    taskList.innerHTML = '<li class="empty-state">No tienes tareas pendientes. ¡Todo al día!</li>';
    return;
  }

  taskList.innerHTML = tasks.map(t => `
    <li class="task-item ${t.done ? 'done' : ''}" data-id="${t.id}">
      <div class="task-left">
        <div class="task-check" onclick="toggleTask(${t.id}, '${escapeHtml(t.title)}')">
          ${t.done ? '✓' : ''}
        </div>
        <span class="task-title">${escapeHtml(t.title)}</span>
      </div>
      <span class="prio-tag prio-${t.priority}">
        ${t.priority >= 4 ? '🚨 Urgente' : (t.priority === 3 ? '🔥 Alta' : (t.priority === 2 ? '⚡ Normal' : '☕ Baja'))}
      </span>
    </li>
  `).join('');
}

btnAddTask.addEventListener('click', async () => {
  const title = newTaskInput.value.trim();
  if (!title) return;
  const priority = parseInt(newTaskPriority.value);
  newTaskInput.value = '';

  try {
    const resp = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, priority })
    });
    const res = await resp.json();
    showToast(res.message || `Tarea guardada en Google & Vikunja`);
    speakResponse(res.message || 'Tarea guardada. ¡Vamos con todo!');
    loadTasks();
  } catch (e) {
    showToast('Error añadiendo tarea', 'error');
  }
});

btnRefreshTasks.addEventListener('click', () => {
  loadTasks();
  showToast('Tareas actualizadas');
});

// v0.10: sincronización bidireccional tareas <-> Google Calendar
btnSyncCal.addEventListener('click', async () => {
  btnSyncCal.textContent = '⏳';
  try {
    const resp = await fetch('/api/sync/calendario', { method: 'POST' });
    const res = await resp.json();
    showToast(res.message || 'Sincronización lista');
    speakResponse(res.message || 'Sincronización lista');
    loadTasks();
  } catch (e) {
    showToast('Error sincronizando con Google Calendar', 'error');
  } finally {
    btnSyncCal.textContent = '🔄';
  }
});

window.toggleTask = async function(id, title) {
  try {
    const resp = await fetch('/api/tasks/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: String(id) })
    });
    const res = await resp.json();
    showToast(res.message || 'Tarea completada');
    speakResponse(res.message || '¡Excelente! Marqué la tarea como completada.');
    loadTasks();
  } catch (e) {
    showToast('Error al completar tarea', 'error');
  }
};

// --- v0.11: Memoria / Notas rápidas ---
async function loadNotas() {
  const consulta = notaBuscarInput.value.trim();
  try {
    const url = consulta ? '/api/notas?q=' + encodeURIComponent(consulta) : '/api/notas';
    const resp = await fetch(url);
    const data = await resp.json();
    renderNotas(data.notas || [], !!consulta);
  } catch (e) {
    notasList.innerHTML = '<div class="empty-state">No se pudo cargar la memoria.</div>';
  }
}

function renderNotas(notas, esBusqueda) {
  if (!notas || notas.length === 0) {
    notasList.innerHTML = esBusqueda
      ? '<div class="empty-state">Sin resultados. Prueba con otras palabras.</div>'
      : '<div class="empty-state">Aún no tienes notas. Anota ideas, códigos o datos y búscalos cuando los necesites.</div>';
    return;
  }

  notasList.innerHTML = notas.map(n => {
    const fecha = (n.creado || '').replace('T', ' ').slice(0, 16);
    return `
      <div class="nota-item">
        <div class="nota-texto">${escapeHtml(n.texto)}</div>
        <div class="nota-meta">
          <span class="nota-fecha">🕒 ${fecha}${n.fuente === 'voz' ? ' · 🎙️ por voz' : ''}</span>
          <button class="nota-borrar" onclick="borrarNota(${n.id})" title="Eliminar nota">🗑</button>
        </div>
      </div>
    `;
  }).join('');
}

btnGuardarNota.addEventListener('click', async () => {
  const texto = notaInput.value.trim();
  if (!texto) return;
  notaInput.value = '';
  try {
    const resp = await fetch('/api/notas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto, fuente: 'panel' })
    });
    const res = await resp.json();
    showToast(res.message || 'Nota guardada');
    speakResponse('Nota guardada en tu memoria.');
    loadNotas();
  } catch (e) {
    showToast('Error guardando la nota', 'error');
  }
});

notaInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') btnGuardarNota.click();
});

let buscarTimeout = null;
notaBuscarInput.addEventListener('input', () => {
  clearTimeout(buscarTimeout);
  buscarTimeout = setTimeout(loadNotas, 350);
});

btnRefreshNotas.addEventListener('click', () => {
  notaBuscarInput.value = '';
  loadNotas();
  showToast('Memoria actualizada');
});

window.borrarNota = async function(id) {
  try {
    const resp = await fetch('/api/notas/' + id, { method: 'DELETE' });
    const res = await resp.json();
    showToast(res.message || 'Nota eliminada');
    loadNotas();
  } catch (e) {
    showToast('Error eliminando la nota', 'error');
  }
};

// --- v0.11: Briefing diario ---
btnBriefing.addEventListener('click', pedirBriefing);
btnEscucharBriefing.addEventListener('click', () => speakResponse(ultimoBriefing));
btnCerrarBriefing.addEventListener('click', cerrarBriefing);
btnCerrarBriefing2.addEventListener('click', cerrarBriefing);
briefingModal.addEventListener('click', (e) => {
  if (e.target === briefingModal) cerrarBriefing();
});

async function pedirBriefing() {
  try {
    showToast('Preparando tu resumen...');
    const resp = await fetch('/api/briefing');
    const res = await resp.json();
    ultimoBriefing = res.texto || '';
    mostrarBriefing(ultimoBriefing);
    speakResponse(ultimoBriefing);
  } catch (e) {
    showToast('No pude preparar el resumen', 'error');
  }
}

function mostrarBriefing(texto) {
  if (!texto) return;
  briefingTexto.innerHTML = texto
    .split(/(?<=[.!?])\s+/)
    .map(f => `<p>${escapeHtml(f.trim())}</p>`)
    .join('');
  briefingModal.classList.remove('hidden');
}

function cerrarBriefing() {
  briefingModal.classList.add('hidden');
  window.speechSynthesis && window.speechSynthesis.cancel();
}

// --- v0.12: Estado del sistema ---
async function loadSalud() {
  try {
    const resp = await fetch('/api/salud');
    const s = await resp.json();

    if (versionTag) versionTag.textContent = s.version || '?';
    if (saludUptime) saludUptime.textContent = `En línea hace ${Math.round((s.uptime_seg || 0) / 60)} min`;

    const chips = [
      { ok: s.voz && s.voz.tts_disponible, label: `Voz: ${s.voz ? s.voz.perfil_activo : '?'}`, detalle: s.voz ? `${s.voz.audios_en_cache} en caché` : '' },
      { ok: s.groq_configurado, label: 'Groq (cerebro)', detalle: s.groq_configurado ? 'activo' : 'sin clave .env' },
      { ok: s.calendario_autenticado, label: 'Google Calendar', detalle: s.calendario_autenticado ? 'conectado' : 'sin token' },
      { ok: s.vikunja_configurado, label: 'Vikunja', detalle: s.vikunja_configurado ? 'conectado' : 'no configurado' },
      { ok: true, label: `Tareas: ${s.tareas_pendientes || 0}`, detalle: '' },
      { ok: true, label: `Notas: ${s.notas_guardadas || 0}`, detalle: '' },
      { ok: true, label: `Herramientas MCP: ${s.herramientas || 0}`, detalle: '' }
    ];

    saludList.innerHTML = chips.map(c => `
      <div class="salud-chip ${c.ok ? 'ok' : 'warn'}">
        <span class="salud-dot">${c.ok ? '✓' : '!'}</span>
        <span class="salud-label">${escapeHtml(c.label)}${c.detalle ? ` <small>· ${escapeHtml(c.detalle)}</small>` : ''}</span>
      </div>
    `).join('');
  } catch (e) {
    if (saludList) saludList.innerHTML = '<div class="empty-state">Sin diagnóstico (¿servidor activo?).</div>';
  }
}

btnSaludTop.addEventListener('click', () => {
  loadSalud();
  document.querySelector('.salud-card').scrollIntoView({ behavior: 'smooth' });
});

// --- Timers Management ---
async function loadTimers() {
  try {
    const resp = await fetch('/api/timers');
    const timers = await resp.json();
    if (!timers || timers.length === 0) {
      timersList.innerHTML = '<div class="empty-state">No hay alarmas activas en este momento.</div>';
    } else {
      timersList.innerHTML = timers.map(t => `
        <div class="timer-item">
          <span>🔔 ${escapeHtml(t.label)}</span>
          <span class="timer-time" title="${escapeHtml(t.target_fecha || '')}">${t.target_time}${t.target_fecha ? ' 📅' : ''}</span>
        </div>
      `).join('');
    }
  } catch (e) {}
}

// --- Audio & Noise Generator ---
function setupNoisePresets() {
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const type = this.getAttribute('data-noise');
      document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      startNoise(type);
    });
  });

  btnStopAudio.addEventListener('click', stopAllAudio);

  volumeSlider.addEventListener('input', (e) => {
    const vol = parseFloat(e.target.value);
    audioStream.volume = vol;
    if (noiseGainNode) noiseGainNode.gain.value = vol;
  });
}

function startNoise(type) {
  stopAllAudio();
  if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
  if (audioContext.state === 'suspended') audioContext.resume();

  activeNoiseType = type;
  const bufferSize = audioContext.sampleRate * 2;
  const noiseBuffer = audioContext.createBuffer(1, bufferSize, audioContext.sampleRate);
  const output = noiseBuffer.getChannelData(0);

  if (type === 'brown') {
    let lastOut = 0.0;
    for (let i = 0; i < bufferSize; i++) {
      const white = Math.random() * 2 - 1;
      output[i] = (lastOut + (0.02 * white)) / 1.02;
      lastOut = output[i];
      output[i] *= 3.5; // Gain
    }
  } else if (type === 'pink') {
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (let i = 0; i < bufferSize; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + white * 0.0555179;
      b1 = 0.99332 * b1 + white * 0.0750759;
      b2 = 0.96900 * b2 + white * 0.1538520;
      b3 = 0.86650 * b3 + white * 0.3104856;
      b4 = 0.55000 * b4 + white * 0.5329522;
      b5 = -0.7616 * b5 - white * 0.0168980;
      output[i] = b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362;
      output[i] *= 0.11;
      b6 = white * 0.115926;
    }
  } else {
    // White noise
    for (let i = 0; i < bufferSize; i++) {
      output[i] = Math.random() * 2 - 1;
    }
  }

  const whiteNoise = audioContext.createBufferSource();
  whiteNoise.buffer = noiseBuffer;
  whiteNoise.loop = true;

  noiseGainNode = audioContext.createGain();
  noiseGainNode.gain.value = parseFloat(volumeSlider.value);

  whiteNoise.connect(noiseGainNode);
  noiseGainNode.connect(audioContext.destination);
  whiteNoise.start(0);
  noiseNode = whiteNoise;

  const names = { brown: 'Ruido Marrón (Enfoque TDAH)', white: 'Ruido Blanco', pink: 'Ruido Rosa' };
  playerTitle.textContent = names[type] || 'Generador de Ruido';
  playerBadge.textContent = 'Generando en Vivo';
}

youtubeForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = ytQuery.value.trim();
  if (!query) return;
  ytQuery.value = '';

  playerTitle.textContent = `Buscando: "${query}"...`;
  playerBadge.textContent = 'Extrayendo Stream';

  try {
    const resp = await fetch('/api/audio/youtube', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    const data = await resp.json();
    handleYoutubePlayback(data);
  } catch (e) {
    playerTitle.textContent = 'Error buscando en YouTube';
  }
});

function handleYoutubePlayback(data) {
  if (data.stream_url) {
    stopAllAudio();
    playerTitle.textContent = data.title || 'YouTube Stream';
    playerBadge.textContent = 'Reproduciendo en Vivo';

    audioStream.src = data.stream_url;
    audioStream.volume = parseFloat(volumeSlider.value);
    audioStream.play().catch(e => console.warn('Audio play prevented:', e));
    showToast(`▶ ${data.title}`);
  }
}

function stopAllAudio() {
  if (audioStream) {
    audioStream.pause();
    audioStream.src = '';
  }
  if (noiseNode) {
    try { noiseNode.stop(); } catch (e) {}
    noiseNode.disconnect();
    noiseNode = null;
  }
  playerTitle.textContent = 'Sin reproducción activa';
  playerBadge.textContent = 'Detenido';
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
}

// --- Utilities ---
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function escapeHtml(text) {
  if (!text) return '';
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
