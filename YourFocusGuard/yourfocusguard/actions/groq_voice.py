"""Interacción de voz y conversación estilo Muse con Groq (v0.8.2).

Incluye:
- Captura de micrófono y transcripción ultrarrápida con Groq Whisper.
- Diálogo conversacional con personalidad Muse (apoyo para TDAH, frases breves y afectuosas).
- Clasificación de intención para preguntas del sistema ("¿sigues en la tarea?").
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from yourfocusguard import __version__

log = logging.getLogger(__name__)

URL_TRANSCRIPCION_GROQ = "https://api.groq.com/openai/v1/audio/transcriptions"
URL_CHAT_GROQ = "https://api.groq.com/openai/v1/chat/completions"
MODELO_WHISPER = "whisper-large-v3-turbo"
# v0.8.4: cadena de LLM actualizada con modelos oficiales activos en Groq
# (llama-3.3-70b-versatile y llama-3.1-8b-instant fueron decomisionados en agosto 2026).
MODELOS_LLM = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
USER_AGENT = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) YourFocusGuard/{__version__}"

PROMPT_SISTEMA_MUSE = (
    "Eres Muse, una mascota virtual tierna, alegre y empática diseñada como compañera de enfoque "
    "para una persona con TDAH. Tu objetivo es animar, acompañar y ayudar a mantener el foco "
    "sin dar sermones ni respuestas largas. Responde SIEMPRE en español, en 1 sola frase corta "
    "(máximo 15-20 palabras), con tono cariñoso, amigable y motivador."
)

#: Alucinaciones típicas de OpenAI Whisper ante silencio o ruido de fondo leve
ALUCINACIONES_SILENCIO = {
    "gracias", "gracias.", "¡gracias!", "gracias a todos", "gracias por ver",
    "thank you", "thank you.", "thank you very much", "thanks for watching",
    "subtítulos por", "subtitulado por", "subtitulos por", "de nada", "amén", "amen", "bye", "adios",
}


def es_transcripcion_valida(texto: str) -> bool:
    """Verifica si la transcripción de Whisper contiene un mensaje real y no una alucinación de silencio.

    Conserva comandos válidos de una sola palabra (ej: 'pausa', 'sí', 'no', 'ok', 'hola').
    """
    if not texto or not texto.strip():
        return False
    t_limpio = texto.strip().lower().strip("¡!¿?.,;:")
    if not t_limpio:
        return False
    if t_limpio in ALUCINACIONES_SILENCIO:
        return False
    for alu in ("subtitulos por", "subtítulos por", "gracias por", "thanks for"):
        if t_limpio.startswith(alu):
            return False
    return True


def obtener_api_key_groq() -> str:
    """Lee GROQ_API_KEY priorizando el archivo .env del proyecto para evitar claves viejas."""
    # Respetar mocks de testing si aplican
    env_val = os.environ.get("GROQ_API_KEY", "").strip()
    if env_val.startswith("gsk_test_"):
        return env_val

    # 1. Priorizar .env del proyecto
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    if os.path.isfile(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY=") or line.startswith("GROQ_API_KEY ="):
                        k = line.split("=", 1)[1].strip().strip("\"'")
                        if k:
                            return k
        except Exception:
            pass

    # 2. Variable de entorno del sistema
    return env_val


def grabar_audio(
    segundos: float = 10.0,
    samplerate: int = 16000,
    umbral_rms: float = 350.0,
    silencio_fin_seg: float = 1.8,
    interrumpir_tts: bool = True,
) -> bytes | None:
    """Graba audio desde el micrófono con soporte para Barge-In (interrupción de TTS) y corte por silencio."""
    try:
        import sounddevice as sd
        import scipy.io.wavfile as wavfile
        import numpy as np

        chunk_seg = 0.2
        chunk_frames = int(chunk_seg * samplerate)
        max_chunks = max(1, int(segundos / chunk_seg))
        silencio_max_chunks = int(silencio_fin_seg / chunk_seg)

        chunks: list[np.ndarray] = []
        hablo = False
        silencio_consecutivo = 0

        # Intentar streaming con InputStream para VAD reactivo y Barge-In
        try:
            with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16") as stream:
                for _ in range(max_chunks):
                    data, _ = stream.read(chunk_frames)
                    chunks.append(data)
                    rms = float(np.sqrt(np.mean(data.astype(float) ** 2))) if len(data) > 0 else 0.0
                    if rms > umbral_rms:
                        hablo = True
                        silencio_consecutivo = 0
                        if interrumpir_tts:
                            try:
                                from yourfocusguard.actions import tts
                                if tts.is_speaking():
                                    tts.detener_reproduccion()
                            except Exception:
                                pass
                    elif hablo:
                        silencio_consecutivo += 1
                        if silencio_consecutivo >= silencio_max_chunks:
                            # Corte temprano: el usuario terminó de responder
                            break
        except Exception:
            # Fallback a sd.rec si InputStream no está disponible en este dispositivo/mock
            frames = int(segundos * samplerate)
            audio = sd.rec(frames, samplerate=samplerate, channels=1, dtype="int16")
            sd.wait()
            chunks = [audio]

        if not chunks:
            return None

        audio_total = np.concatenate(chunks, axis=0)
        max_amp = float(np.max(np.abs(audio_total))) if len(audio_total) > 0 else 0.0
        if max_amp < umbral_rms:
            log.debug("Audio descartado: nivel demasiado bajo (%s)", max_amp)
            return None

        bio = io.BytesIO()
        wavfile.write(bio, samplerate, audio_total)
        return bio.getvalue()
    except Exception as exc:
        log.warning("No se pudo grabar audio: %s", exc)
        return None


def transcribir_con_groq(
    wav_bytes: bytes,
    api_key: str | None = None,
    timeout: float = 12.0,
) -> str:
    """Envía un archivo WAV a la API Whisper de Groq para obtener el texto."""
    key = api_key or obtener_api_key_groq()
    if not key:
        raise ValueError("GROQ_API_KEY no encontrada")

    boundary = f"----WebKitFormBoundary{int(time.time() * 1000)}"
    crlf = b"\r\n"

    partes = []
    # Campo model
    partes.append(f"--{boundary}".encode("utf-8") + crlf)
    partes.append(b'Content-Disposition: form-data; name="model"' + crlf + crlf)
    partes.append(MODELO_WHISPER.encode("utf-8") + crlf)

    # Campo language (español para óptima precisión y latencia)
    partes.append(f"--{boundary}".encode("utf-8") + crlf)
    partes.append(b'Content-Disposition: form-data; name="language"' + crlf + crlf)
    partes.append(b"es" + crlf)

    # Campo file
    partes.append(f"--{boundary}".encode("utf-8") + crlf)
    partes.append(
        b'Content-Disposition: form-data; name="file"; filename="audio.wav"' + crlf
    )
    partes.append(b"Content-Type: audio/wav" + crlf + crlf)
    partes.append(wav_bytes + crlf)
    partes.append(f"--{boundary}--".encode("utf-8") + crlf)

    cuerpo = b"".join(partes)

    req = urllib.request.Request(
        URL_TRANSCRIPCION_GROQ,
        data=cuerpo,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(cuerpo)),
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        texto = str(res.get("text", "")).strip()

        # Trazabilidad de segundos de audio Whisper (coste aproximado $0.002/min = $0.000033/s)
        try:
            from yourfocusguard.core.events import EVT_CONSUMO_API, publish
            segundos_audio = round(len(wav_bytes) / 32000.0, 2)
            coste_whisper = round(segundos_audio * 0.000033, 5)
            publish(EVT_CONSUMO_API, {
                "segundos_audio": segundos_audio,
                "tokens_llm": 0,
                "coste_estimado": coste_whisper,
            })
        except Exception:
            pass

        # v0.8.4: descartar alucinaciones de silencio de Whisper
        if not es_transcripcion_valida(texto):
            log.debug("Transcripción descartada por alucinación de silencio: %r", texto)
            return ""

        return texto


def obtener_endpoint_llm_local() -> str | None:
    """Devuelve la URL del endpoint local OpenAI-compatible (Ollama / LM Studio) si está disponible."""
    url = os.environ.get("LOCAL_LLM_URL", "").strip()
    if url:
        return url if "/chat/completions" in url else f"{url.rstrip('/')}/v1/chat/completions"

    host = os.environ.get("OLLAMA_HOST", "").strip()
    if host:
        return f"{host.rstrip('/')}/v1/chat/completions"

    return None


def consultar_llm_local(
    mensajes: list[dict[str, str]],
    modelo: str = "llama3",
    endpoint: str | None = None,
    timeout: float = 6.0,
) -> str | None:
    """Consulta un LLM local compatible con OpenAI API (Ollama, LM Studio, etc.)."""
    url = endpoint or obtener_endpoint_llm_local()
    if not url:
        return None

    payload = {
        "model": modelo,
        "messages": mensajes,
        "temperature": 0.6,
        "max_tokens": 50,
    }
    cuerpo = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=cuerpo,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(cuerpo)),
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return str(data["choices"][0]["message"]["content"]).strip()
    except Exception as exc:
        log.debug("LLM local no disponible en %s: %s", url, exc)
        return None


def conversar_con_muse(
    texto_usuario: str,
    api_key: str | None = None,
    timeout: float = 8.0,
    modo_privado: bool = False,
) -> str:
    """Genera una respuesta afectuosa y concisa con personalidad Muse (TDAH).

    Soporta inferencia local vía Ollama / LM Studio y fallback en nube con Groq.
    """
    if not texto_usuario.strip():
        return "¡Aquí estoy contigo! ¡A por ello!"

    # 1. Priorizar LLM local si está configurado
    endpoint_local = obtener_endpoint_llm_local()
    if endpoint_local:
        resp_local = consultar_llm_local(
            [
                {"role": "system", "content": PROMPT_SISTEMA_MUSE},
                {"role": "user", "content": texto_usuario},
            ],
            endpoint=endpoint_local,
            timeout=timeout,
        )
        if resp_local:
            return resp_local

    if modo_privado:
        return "¡Aquí estoy contigo en silencio! ¡Sigamos enfocados!"

    key = api_key or obtener_api_key_groq()
    if not key:
        return "¡Aquí estoy contigo! ¡A por ello!"

    for modelo in MODELOS_LLM:
        payload = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": PROMPT_SISTEMA_MUSE},
                {"role": "user", "content": texto_usuario},
            ],
            "temperature": 0.6,
            "max_tokens": 45,
        }
        cuerpo = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            URL_CHAT_GROQ,
            data=cuerpo,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Content-Length": str(len(cuerpo)),
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                contenido = data["choices"][0]["message"]["content"].strip()
                # Trazabilidad de tokens de LLM
                try:
                    from yourfocusguard.core.events import EVT_CONSUMO_API, publish
                    tokens = int(data.get("usage", {}).get("total_tokens", 45))
                    coste = round(tokens * 0.0000008, 6)
                    publish(EVT_CONSUMO_API, {
                        "segundos_audio": 0.0,
                        "tokens_llm": tokens,
                        "coste_estimado": coste,
                    })
                except Exception:
                    pass
                return contenido
        except urllib.error.HTTPError as exc:
            det = exc.read().decode("utf-8", errors="replace")
            # v0.8.4: Solo 401 (Unauthorized) y 403 (Forbidden) abortan la cadena;
            # 404 (model not found), 410 (gone/deprecated), 429 (rate limit) y 5xx prueban el siguiente modelo.
            if exc.code in (401, 403):
                log.warning("Error de autenticación/permisos HTTP %d en Groq: %s", exc.code, det[:180])
                break
            log.debug("Error HTTP %d en modelo Groq %s (%s), intentando siguiente...", exc.code, modelo, det[:100])
            continue
        except Exception as exc:
            log.warning("Fallo al conversar con Groq Muse (%s): %s", modelo, exc)
            continue

    return "No pude conectar con mi cabeza en la nube, ¡pero aquí sigo contigo!"


def clasificar_intencion_local(texto_usuario: str, opciones: list[str]) -> str | None:
    """Clasifica intenciones comunes en 0 ms usando heurísticas y regex locales.

    Ahorra latencia de red (de ~1200ms a 0ms), tokens de Groq y privacidad.
    """
    if not texto_usuario or not opciones:
        return None

    txt = texto_usuario.lower().strip()

    # 1. Búsqueda directa de la opción exacta en el texto
    for op in opciones:
        if op.lower() in txt:
            return op

    # 2. Heurística de intenciones comunes
    patrones_afirmacion = {"si", "sí", "claro", "por supuesto", "afirmativo", "correcto", "exacto", "vale", "dale", "ok", "yes", "sep", "sip"}
    patrones_negacion = {"no", "negativo", "para nada", "ahora no", "nunca", "nop"}
    patrones_foco = {"sigo", "aquí", "estoy", "trabajando", "tarea", "en ello", "estudiando", "leyendo", "programando", "editando"}
    patrones_pausa = {"pausa", "descanso", "quince", "minutos", "parar", "un break", "recreo", "café", "almorzar", "comer"}
    patrones_ignorar = {"luego", "despues", "después", "tarde", "mas tarde", "más tarde", "posponer", "lueguito"}

    palabras = set(txt.replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ").split())
    opciones_low = [(o, o.lower()) for o in opciones]

    if palabras & patrones_ignorar:
        for op_orig, op_low in opciones_low:
            if any(p in op_low for p in ["luego", "después", "posponer"]):
                return op_orig

    if palabras & patrones_foco:
        for op_orig, op_low in opciones_low:
            if any(p in op_low for p in ["sigo", "tarea", "trabajando", "foco", "concentrado", "aquí"]):
                return op_orig

    if palabras & patrones_pausa:
        for op_orig, op_low in opciones_low:
            if any(p in op_low for p in ["pausa", "descanso", "min", "break"]):
                return op_orig

    if palabras & patrones_afirmacion:
        for op_orig, op_low in opciones_low:
            if any(p in op_low for p in ["sí", "si", "agregar", "mantener", "permitir", "continuar"]):
                return op_orig

    if palabras & patrones_negacion:
        for op_orig, op_low in opciones_low:
            if any(p in op_low for p in ["no", "distracción", "distraccion", "cerrar", "bloquear"]):
                return op_orig

    return None


def clasificar_intencion_groq(
    texto_usuario: str,
    contexto_pregunta: str,
    opciones: list[str],
    api_key: str | None = None,
    timeout: float = 8.0,
    usar_local: bool = True,
) -> str | None:
    """Clasifica la respuesta verbal del usuario seleccionando una de las opciones válidas."""
    if not texto_usuario.strip():
        return None

    # 1. Clasificación local inmediata si está habilitada (0ms de latencia, 0 tokens)
    if usar_local:
        coincidencia = clasificar_intencion_local(texto_usuario, opciones)
        if coincidencia:
            log.info("Intención clasificada localmente (0ms): '%s' -> '%s'", texto_usuario, coincidencia)
            return coincidencia

    key = api_key or obtener_api_key_groq()
    if not key:
        texto_l = texto_usuario.lower()
        for op in opciones:
            if op.lower() in texto_l:
                return op
        return None

    prompt = (
        f"El usuario escuchó la pregunta: '{contexto_pregunta}'.\n"
        f"El usuario respondió por voz: '{texto_usuario}'.\n"
        f"Selecciona exactamente una de las siguientes opciones válidas que mejor represente su intención: {opciones}.\n"
        f"Responde ÚNICAMENTE con el texto exacto de la opción seleccionada, sin explicaciones ni puntuación adicional."
    )

    for modelo in MODELOS_LLM:
        payload = {
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 15,
        }
        cuerpo = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            URL_CHAT_GROQ,
            data=cuerpo,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Content-Length": str(len(cuerpo)),
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                eleccion = data["choices"][0]["message"]["content"].strip()
                for op in opciones:
                    if op.lower() in eleccion.lower() or eleccion.lower() in op.lower():
                        return op
                return eleccion
        except urllib.error.HTTPError as exc:
            det = exc.read().decode("utf-8", errors="replace")
            # v0.8.4: Solo 401/403 abortan; 404, 410, 429 y 5xx prueban siguiente modelo
            if exc.code in (401, 403):
                log.warning("Error de autenticación/permisos HTTP %d en Groq Clasificador: %s", exc.code, det[:180])
                break
            log.debug("Error HTTP %d en Groq Clasificador (%s), intentando siguiente...", exc.code, modelo)
            continue
        except Exception as exc:
            log.warning("Fallo al clasificar con Groq LLM (%s): %s", modelo, exc)
            continue

    return None


def es_intencion_nota(texto: str) -> bool:
    """Detecta si la frase del usuario es una intención de captura rápida / brain dump (v0.8.3 Fase 2)."""
    t = (texto or "").strip().lower()
    if not t:
        return False
    frases_clave = (
        "anota", "apunta", "nota", "idea", "recordar", "recuerda",
        "no olvidar", "guarda", "guardar", "inbox"
    )
    for f in frases_clave:
        if t.startswith(f) or f" {f} " in f" {t} ":
            return True
    return False


def hablar_con_mascota_async(segundos: float = 8.0, modo_privado: bool = False) -> None:
    """Inicia en segundo plano la captura por micrófono, transcripción y respuesta hablada.

    v0.8.3: con ``modo_privado=True`` NO se abre el micrófono y NO se contacta
    a ninguna nube (ni Whisper ni LLM): se informa por burbuja y se termina.
    """
    def _proceso():
        try:
            from yourfocusguard.actions import tts
            from yourfocusguard.core.events import EVT_PET_REACTION, EVT_PET_SAY, publish

            if modo_privado:
                log.info("Modo privado activo: diálogo por voz anulado (0 micrófono, 0 nube).")
                publish(EVT_PET_SAY, {
                    "texto": "Estoy en modo privado: sin voz por ahora. 🤫",
                    "reaccion": "waiting",
                    "duracion_ms": 4000,
                })
                publish(EVT_PET_REACTION, "waiting")
                return

            publish(EVT_PET_REACTION, "listening")
            publish(EVT_PET_SAY, {
                "texto": "🎤 Te escucho...",
                "reaccion": "listening",
                "duracion_ms": int(segundos * 1000),
            })

            audio_bytes = grabar_audio(segundos=segundos)
            if not audio_bytes:
                publish(EVT_PET_SAY, {
                    "texto": "No te escuché bien. ¡Aquí sigo!",
                    "reaccion": "idle",
                    "duracion_ms": 3000,
                })
                publish(EVT_PET_REACTION, "idle")
                return

            publish(EVT_PET_SAY, {
                "texto": "Pensando...",
                "reaccion": "thinking",
                "duracion_ms": 2500,
            })
            transcripcion = transcribir_con_groq(audio_bytes)
            log.info("Usuario dijo a Muse: '%s'", transcripcion)

            if not transcripcion.strip():
                publish(EVT_PET_SAY, {
                    "texto": "No entendí bien, ¡aquí sigo!",
                    "reaccion": "idle",
                    "duracion_ms": 3000,
                })
                publish(EVT_PET_REACTION, "idle")
                return

            from yourfocusguard.actions.musica_foco import (
                ajustar_volumen,
                detener_musica_foco,
                es_intencion_detener_musica,
                es_intencion_musica,
                iniciar_musica_foco,
            )
            from yourfocusguard.core.scheduler import extraer_recordatorio_voz, obtener_scheduler
            from yourfocusguard.integrations.vikunja import crear_tarea, es_intencion_agenda

            es_rec, tarea, minutos = extraer_recordatorio_voz(transcripcion)
            if es_intencion_musica(transcripcion):
                if es_intencion_detener_musica(transcripcion):
                    detener_musica_foco()
                    respuesta = "¡Música detenida! Seguimos concentrados."
                elif "volumen" in transcripcion.lower():
                    import re
                    match_vol = re.search(r"(\d{1,3})", transcripcion)
                    if match_vol:
                        v = float(match_vol.group(1)) / 100.0
                        ajustar_volumen(v)
                        respuesta = f"Ajusté el volumen al {int(v*100)}%."
                    elif "sube" in transcripcion.lower() or "aumenta" in transcripcion.lower():
                        ajustar_volumen(0.8)
                        respuesta = "Subí el volumen de la música."
                    else:
                        ajustar_volumen(0.3)
                        respuesta = "Bajé el volumen de la música."
                else:
                    tipo = "blanco" if "blanco" in transcripcion.lower() else "marron"
                    ok, msg = iniciar_musica_foco(tipo=tipo)
                    respuesta = "¡Ruido de concentración activado! 🎧" if ok else msg
            elif es_rec:
                scheduler = obtener_scheduler()
                scheduler.programar(tarea, minutos)
                min_texto = f"{int(minutos)} minutos" if minutos == int(minutos) else f"{minutos:.1f} minutos"
                respuesta = f"¡Entendido! Te recordaré en {min_texto}: {tarea}."
            elif es_intencion_agenda(transcripcion):
                import re
                tiene_hora = bool(re.search(r"\b(?:\d{1,2}(?::\d{2})?|\d{1,2}\s*(?:am|pm|de la mañana|de la tarde|de la noche))\b", transcripcion, re.IGNORECASE))
                if not tiene_hora:
                    if "mañana" in transcripcion.lower():
                        respuesta = "¿A qué hora te hago el acuerdo mañana?"
                    else:
                        dias = ["lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo"]
                        dia_encontrado = next((d for d in dias if d in transcripcion.lower()), None)
                        if dia_encontrado:
                            respuesta = f"¿A qué hora comienza el evento el {dia_encontrado}?"
                        else:
                            respuesta = "¿A qué hora te programo el evento?"

                    publish(EVT_PET_SAY, {
                        "texto": respuesta,
                        "reaccion": "speaking",
                        "duracion_ms": 6000,
                    })
                    tts.speak(respuesta)
                    return

                from yourfocusguard.integrations.vikunja import limpiar_texto_agenda
                titulo_tarea = limpiar_texto_agenda(transcripcion)
                respuesta = f"¿Agendo '{titulo_tarea}'?"

                publish(EVT_PET_SAY, {
                    "texto": respuesta,
                    "reaccion": "waiting",
                    "opciones": ["Agendar", "Cancelar"],
                    "auto_confirmar_seg": 15,
                    "duracion_ms": 16000,
                })
                tts.speak(respuesta)

                def _auto_ejecutar():
                    cancelado = False
                    for _ in range(30):
                        time.sleep(0.5)
                        try:
                            from yourfocusguard.panel import pet_consumir_respuestas
                            respuestas = [str(r).strip().lower() for r in pet_consumir_respuestas()]
                            if any(r in ("cancelar", "cancel", "no") for r in respuestas):
                                cancelado = True
                                break
                            if any(r in ("agendar", "confirmar", "sí", "si") for r in respuestas):
                                break
                        except Exception:
                            pass

                    if cancelado:
                        publish(EVT_PET_SAY, {"texto": "Cancelado. No agendé nada.", "reaccion": "idle", "duracion_ms": 3000})
                        return

                    try:
                        from yourfocusguard.config import load_config
                        cfg = load_config()
                        vk_cfg = getattr(cfg, "vikunja", None)
                    except Exception:
                        vk_cfg = None

                    if vk_cfg and vk_cfg.habilitado and vk_cfg.url and vk_cfg.token:
                        ok, msg = crear_tarea(transcripcion, cfg=vk_cfg)
                        if ok:
                            publish(EVT_PET_SAY, {"texto": f"¡Agendado en Vikunja! {msg}", "reaccion": "idle", "duracion_ms": 4000})
                    else:
                        from yourfocusguard.storage.vault import guardar_nota_rapida
                        guardar_nota_rapida(transcripcion)
                        publish(EVT_PET_SAY, {"texto": "¡Agendado en tu diario local! Continúa enfocado. 🚀", "reaccion": "idle", "duracion_ms": 4000})

                threading.Thread(target=_auto_ejecutar, daemon=True).start()
                return
            elif es_intencion_nota(transcripcion):
                from yourfocusguard.storage.vault import guardar_nota_rapida
                exito, resumen, _ = guardar_nota_rapida(transcripcion)
                if exito:
                    respuesta = "¡Anotado en tu diario! Continúa enfocado. 🚀"
                else:
                    respuesta = "Anoté tu idea localmente. ¡Sigue con todo!"
            else:
                respuesta = conversar_con_muse(transcripcion, modo_privado=modo_privado)
            log.info("Muse responde: '%s'", respuesta)

            publish(EVT_PET_SAY, {
                "texto": respuesta,
                "reaccion": "speaking",
                "duracion_ms": 5000,
            })
            tts.speak(respuesta)

        except Exception as exc:
            log.warning("Error en diálogo con mascota: %s", exc)
            try:
                from yourfocusguard.core.events import EVT_PET_REACTION, publish
                publish(EVT_PET_REACTION, "idle")
            except Exception:
                pass

    t = threading.Thread(target=_proceso, name="muse-dialogo", daemon=True)
    t.start()


class AsistenteVozGroq:
    """Gestiona el ciclo de escucha en segundo plano cuando el sistema hace una pregunta."""

    def __init__(self, callback_respuesta: Callable[[str], None] | None = None) -> None:
        self.callback = callback_respuesta
        self._escuchando = False
        self._hilo: threading.Thread | None = None

    def escuchar_y_procesar_async(
        self,
        contexto_pregunta: str,
        opciones: list[str],
        segundos: float = 10.0,
        al_finalizar: Callable[[str | None], None] | None = None,
    ) -> None:
        if self._escuchando:
            return

        def _trabajo():
            self._escuchando = True
            try:
                # Esperar a que el TTS termine de hablar antes de abrir micrófono
                from yourfocusguard.actions import tts
                for _ in range(50):
                    if not tts.is_speaking():
                        break
                    time.sleep(0.1)

                log.info("Iniciando captura de voz tras pregunta (%s s)...", segundos)
                audio_bytes = grabar_audio(segundos=segundos)
                if not audio_bytes:
                    if al_finalizar:
                        al_finalizar(None)
                    return

                texto = transcribir_con_groq(audio_bytes)
                log.info("Transcripción Groq: '%s'", texto)
                if not texto:
                    if al_finalizar:
                        al_finalizar(None)
                    return

                intencion = clasificar_intencion_groq(texto, contexto_pregunta, opciones)
                log.info("Intención reconocida: %s", intencion)
                if self.callback and intencion:
                    self.callback(intencion)
                if al_finalizar:
                    al_finalizar(intencion)
            except Exception as exc:
                log.warning("Error en flujo de voz Groq: %s", exc)
                if al_finalizar:
                    al_finalizar(None)
            finally:
                self._escuchando = False

        self._hilo = threading.Thread(target=_trabajo, name="groq-voice", daemon=True)
        self._hilo.start()
