import os
import re
import json
import logging
import urllib.request
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

URL_CHAT_GROQ = "https://api.groq.com/openai/v1/chat/completions"
MODELOS_GROQ = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ADHDAssistant/1.0"


class Router:
    def __init__(self, config=None):
        self.config = config
        self.groq_api_key = self._find_groq_api_key()

    def _find_groq_api_key(self) -> str:
        key = os.getenv("GROQ_API_KEY", "").strip()
        if key:
            return key

        posibles_env = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "YourFocusGuard", ".env"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        ]
        for path in posibles_env:
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("GROQ_API_KEY=") or line.startswith("GROQ_API_KEY ="):
                                return line.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception:
                    pass
        return ""

    def _call_groq_llm(self, prompt: str, temperature: float = 0.2, max_tokens: int = 250) -> str:
        if not self.groq_api_key:
            return ""

        for model in MODELOS_GROQ:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            cuerpo = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                URL_CHAT_GROQ,
                data=cuerpo,
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(cuerpo)),
                    "User-Agent": USER_AGENT,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"Fallo llamando al modelo Groq {model}: {e}")
                continue
        return ""

    def route(self, text: str) -> Dict[str, Any]:
        """Enruta la orden hacia la acción correspondiente con parámetros parseados."""
        texto_lower = text.lower().strip()
        now = datetime.now()
        fecha_ref = now.strftime("%Y-%m-%d %H:%M (Día: %A)")

        # 1. Reglas Rápidas (0 ms)
        # Tareas: Listar
        if any(w in texto_lower for w in ["que me toca", "qué me toca", "que me falta", "qué me falta", "mis pendientes", "mis tareas", "listar tareas", "cronograma", "organizar mis prioridades", "prioridades"]):
            return {"action": "tarea_listar", "text": text}

        # Tareas: Completar
        if any(texto_lower.startswith(w) for w in ["ya termine", "ya terminé", "termine", "terminé", "completar tarea", "tarea lista", "marcar terminada", "listo el", "lista la"]):
            query_task = text
            for pref in ["ya termine", "ya terminé", "termine", "terminé", "completar tarea", "tarea lista", "marcar terminada"]:
                if texto_lower.startswith(pref):
                    query_task = text[len(pref):].strip(" :,-")
                    break
            return {"action": "tarea_completar", "query": query_task}

        # Alarmas / Temporizadores
        if "alarma" in texto_lower or "temporizador" in texto_lower or (("recuerdame" in texto_lower or "recuérdame" in texto_lower) and " en " in texto_lower):
            m_horas = re.search(r'(\d+)\s*(?:hora|horas|h)', texto_lower)
            m_min = re.search(r'(\d+)\s*(?:minuto|minutos|min|m)', texto_lower)
            m_sec = re.search(r'(\d+)\s*(?:segundo|segundos|seg|s)', texto_lower)

            segundos_totales = 0
            if m_horas:
                segundos_totales += int(m_horas.group(1)) * 3600
            if m_min:
                segundos_totales += int(m_min.group(1)) * 60
            if m_sec:
                segundos_totales += int(m_sec.group(1))

            if segundos_totales == 0:
                segundos_totales = 600  # 10 min por defecto

            # Extraer etiqueta
            label = text
            if " que diga " in texto_lower:
                label = text.split(" que diga ", 1)[1]
            elif " de " in texto_lower:
                label = text.split(" de ", 1)[1]

            return {
                "action": "crear_alarma",
                "seconds": segundos_totales,
                "label": label.strip(),
            }

        # Música / Audio
        if any(w in texto_lower for w in ["pon musica", "pon música", "musica", "música", "reproduce", "ruido marron", "ruido marrón", "ruido blanco", "para la musica", "para la música", "stop audio"]):
            if any(w in texto_lower for w in ["para", "stop", "deten", "detén", "silencio"]):
                return {"action": "audio_stop"}
            if "marron" in texto_lower or "marrón" in texto_lower:
                return {"action": "audio_noise", "noise_type": "brown"}
            if "blanco" in texto_lower:
                return {"action": "audio_noise", "noise_type": "white"}
            if "rosa" in texto_lower or "pink" in texto_lower:
                return {"action": "audio_noise", "noise_type": "pink"}

            # Búsqueda en YouTube
            query_music = text
            for pref in ["pon musica de", "pon música de", "pon musica", "pon música", "reproduce", "buscar en youtube", "pon"]:
                if texto_lower.startswith(pref):
                    query_music = text[len(pref):].strip()
                    break
            return {"action": "audio_youtube", "query": query_music or "lofi beats for focus"}

        # 2. Clasificación Inteligente LLM para Calendario vs Nueva Tarea vs Charla
        prompt = f"""Eres el cerebro de un Asistente TDAH.
REFERENCIA: {fecha_ref}, GMT-5.

Frase del usuario: "{text}"

Clasifica la acción en UNA de las siguientes categorías JSON:
1. Si pide agendar una cita/evento con día u hora específica (ej: "cita mañana a las 10am"):
{{"action": "crear_evento", "summary": "...", "start_time": "ISO 8601 con -05:00", "end_time": null}}
2. Si pide anotar un trabajo, pendiente o tarea para hacer (ej: "tengo que entregar el reporte", "nueva tarea comprar pan"):
{{"action": "tarea_crear", "title": "...", "priority": 1 a 4 (3=alta, 2=normal)}}
3. Si es conversación o apoyo de ánimo:
{{"action": "charla", "response": "Respuesta breve y motivadora en 1-2 frases"}}

Responde SOLO el bloque JSON sin comentarios."""

        raw_resp = self._call_groq_llm(prompt, temperature=0.1, max_tokens=200)
        clean = raw_resp
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(clean)
            return parsed
        except Exception:
            return {"action": "charla", "response": "¡Aquí estoy contigo! ¿En qué nos enfocamos hoy?"}
