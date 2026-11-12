// ==============================================================================
// YourFocusGuard ADHD Assistant - Frontend Engine
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
const youtubeForm = document.getElementById('youtubeForm');
const ytQuery = document.getElementById('ytQuery');
const playerTitle = document.getElementById('playerTitle');
const playerBadge = document.getElementById('playerBadge');
const btnStopAudio = document.getElementById('btnStopAudio');
const volumeSlider = document.getElementById('volumeSlider');
const audioStream = document.getElementById('audioStream');
const timersList = document.getElementById('timersList');
const toastContainer = document.getElementById('toastContainer');

// --- Global Audio & Recording State ---
let isRecording = false;
let audioContext = null;
let mediaStream = null;
let analyser = null;
let animationFrameId = null;
let recognition = null;
let recordStartTime = 0;
let timerInterval = null;

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
  setupNoisePresets();
  drawIdleWave();
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

    // Reproducir respuesta por voz si el navegador lo soporta
    speakResponse(data.message);

    // Actualizar secciones según la acción
    if (data.action && data.action.startsWith('tarea')) loadTasks();
    if (data.action === 'crear_alarma') loadTimers();
    if (data.action === 'audio_youtube') handleYoutubePlayback(data);
    if (data.action === 'audio_noise') startNoise(data.noise_type);
    if (data.action === 'audio_stop') stopAllAudio();

  } catch (err) {
    statusIndicator.className = 'status-indicator';
    statusIndicator.textContent = '⚠️ Error conectando con el asistente.';
    showToast('Error procesando comando', 'error');
  }
}

// TTS por voz del navegador
function speakResponse(text) {
  if (!text || !('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'es-ES';
  utterance.rate = 1.05;
  window.speechSynthesis.speak(utterance);
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
    showToast(`Tarea guardada en Google & Vikunja`);
    loadTasks();
  } catch (e) {
    showToast('Error añadiendo tarea', 'error');
  }
});

btnRefreshTasks.addEventListener('click', () => {
  loadTasks();
  showToast('Tareas actualizadas');
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
    loadTasks();
  } catch (e) {
    showToast('Error al completar tarea', 'error');
  }
};

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
          <span class="timer-time">${t.target_time}</span>
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
