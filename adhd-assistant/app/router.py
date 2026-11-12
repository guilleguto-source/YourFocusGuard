import os
import re
import json
import logging
import urllib.request
from datetime import datetime
from typing import Dict, Any

import herramientas
import memoria

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

    # ------------------------------------------------------------------
    # RUTEO
    # ------------------------------------------------------------------
    def route(self, text: str) -> Dict[str, Any]:
        """Enruta la orden hacia la acción correspondiente con parámetros parseados.

        Dos capas:
        1. Reglas rápidas locales (0 ms, sin API): frases típicas TDAH.
        2. Clasificación LLM (Groq) con el prompt generado desde el registro
           de herramientas + el contexto reciente de la memoria (v0.11).
        """
        texto_lower = text.lower().strip()
        now = datetime.now()
        fecha_ref = now.strftime("%Y-%m-%d %H:%M (Día: %A)")

        # ----------------- 1. Reglas Rápidas (0 ms) -----------------

        # Guardarraíl de negación / queja sobre agendamientos ("no te dije que agenda", "no agendes")
        if any(
            re.search(p, texto_lower)
            for p in [
                r"\bno\s+(?:te\s+dije|quiero|agendes|programes|pongas|creas|crees|hagas)\b",
                r"\b(?:no|sin)\s+agendar\b",
                r"\bno\s+(?:lo\s+)?agendes\b",
                r"\bno\s+dije\s+que\b",
                r"\bpor\s+qu[eé]\s+(?:agendaste|programaste)\b",
            ]
        ):
            return {
                "action": "charla",
                "response": "¡Entendido! No agendaré nada. Solo avísame si necesitas algo específico.",
            }

        # Aclaración interactiva si falta la hora al pedir agendar o recordar
        if any(w in texto_lower for w in ["recuerdame", "recuérdame", "acuerdame", "acuérdame", "agenda", "agendar", "cita", "reunion", "reunión"]) and not (" en " in texto_lower and any(u in texto_lower for u in ["minuto", "min", "hora", "segundo"])):
            tiene_hora = bool(re.search(r"\b(?:\d{1,2}(?::\d{2})?|\d{1,2}\s*(?:am|pm|de la mañana|de la tarde|de la noche))\b", texto_lower))
            if not tiene_hora:
                if "mañana" in texto_lower:
                    return {
                        "action": "charla",
                        "response": "¿A qué hora te hago el acuerdo mañana?",
                    }
                for dia in ["lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo"]:
                    if dia in texto_lower:
                        return {
                            "action": "charla",
                            "response": f"¿A qué hora comienza el evento el {dia}?",
                        }

        # Briefing diario (v0.11)
        if any(
            w in texto_lower
            for w in ["resumen del dia", "resumen del día", "briefing", "como va mi dia", "cómo va mi día", "cómo va mi día hoy", "repaso del dia", "repaso del día"]
        ):
            return {"action": "briefing_diario"}

        # Buscar en notas (v0.11)
        if any(
            w in texto_lower
            for w in ["busca en mis notas", "buscar en mis notas", "qué anoté", "que anote", "que anoté", "qué anoté de", "mira en mis notas"]
        ):
            query = text
            for pref in ["busca en mis notas", "buscar en mis notas", "mira en mis notas", "qué anoté de", "que anoté de", "qué anoté", "que anoté", "que anote", "qué anoté sobre", "que anoté sobre"]:
                if texto_lower.startswith(pref):
                    query = text[len(pref):].strip(" :¿?de")
                    break
            if not query:
                query = text
            return {"action": "nota_buscar", "query": query}

        # Tareas: Listar
        if any(w in texto_lower for w in ["que me toca", "qué me toca", "que me falta", "qué me falta", "mis pendientes", "mis tareas", "listar tareas", "cronograma", "organizar mis prioridades", "prioridades"]):
            return {"action": "tarea_listar"}

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
        if any(w in texto_lower for w in ["pon musica", "pon música", "musica", "música", "reproduce", "ruido marron", "ruido marrón", "ruido blanco", "ruido rosa", "ruido pink", "ruido cafe", "ruido café", "para la musica", "para la música", "stop audio"]):
            # FIX v0.12 (bug latente desde v0.9): el stop se detectaba con el
            # substring "para", así que "ruido rosa PARA leer" detenía el audio
            # en vez de activarlo. Ahora solo frases de parada reales.
            if any(w in texto_lower for w in ["para la musica", "para la música", "parar", "stop", "deten", "detén", "silencio", "apaga"]):
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

        # Offline: "anota/apunta que..." sin API key -> nota directa (v0.11)
        if not self.groq_api_key and any(texto_lower.startswith(p) for p in ["anota", "apunta", "anotar que", "registra que"]):
            texto_nota = re.sub(r"^(anota|apunta|anotar que|registra que)\s*(que\s*)?", "", text, flags=re.IGNORECASE).strip()
            if texto_nota:
                return {"action": "nota_crear", "texto": texto_nota}

        # -------- 2. Clasificación Inteligente LLM --------
        # v0.12: las categorías salen del registro de herramientas
        # (herramientas.py), y el prompt incluye la memoria reciente (v0.11)
        # para que "y el viernes?" o "recuérdame lo de ayer" tengan contexto.

        definiciones = herramientas.definiciones_para_llm()
        contexto = memoria.contexto_reciente_texto(6)
        bloque_contexto = (
            f"CONTEXTO RECIENTE del usuario (lo que pidió hace un rato):\n{contexto}\n\n"
            if contexto else ""
        )

        prompt = f"""Eres el cerebro de un Asistente TDAH.
REFERENCIA: {fecha_ref}.

{bloque_contexto}Frase del usuario: "{text}"

Clasifica la acción en UNA de las siguientes categorías JSON:
{definiciones}

Reglas:
- Fechas ("start_time", "due_date") en ISO 8601 con offset -05:00 (ej: {now.year}-11-13T10:00:00-05:00). Si no hay fecha clara, null.
- "priority": 1 a 4 (3=alta, 2=normal). "end_time" puede ser null.
- REGLA CRÍTICA DE AGENDAMIENTO: "crear_evento" y "tarea_crear" requieren una orden explícita e imperativa del usuario (ej: "agenda cita médica mañana a las 10", "agrega tarea comprar pan"). NUNCA clasifiques como crear_evento o tarea_crear ante comentarios casuales, dudas, preguntas ("¿tengo algo agendado?") o menciones pasivas de tiempo. Ante la menor ambigüedad o charla informal, clasifica SIEMPRE como "charla".
- Si un evento tiene hora de inicio pero no especifica fin o duración, calcula "end_time" sumando 1 hora a "start_time". Si no se especificó hora exacta en absoluto, clasifica como "charla" y pregunta amablemente la hora (ej: "¿A qué hora te hago el acuerdo mañana?").
- Importante: tarea_crear es un PENDIENTE por hacer; nota_crear es INFORMACIÓN para recordar (códigos, ideas, datos); crear_evento tiene día/hora de cita.
- Para "charla": "response" breve, cálida y motivadora en 1-2 frases.

Responde SOLO el bloque JSON sin comentarios."""

        raw_resp = self._call_groq_llm(prompt, temperature=0.1, max_tokens=220)
        clean = raw_resp
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(clean)
            # Sanidad: la acción debe existir en el registro (v0.12)
            if parsed.get("action") not in herramientas.nombres():
                return {"action": "charla", "response": "¡Aquí estoy contigo! ¿En qué nos enfocamos hoy?"}
            return parsed
        except Exception:
            # Sin LLM o respuesta inválida: fallback útil
            if not self.groq_api_key:
                return {
                    "action": "charla",
                    "response": "No tengo clave de Groq configurada (.env), así que solo entiendo órdenes rápidas: tareas, alarmas, música, ruido, notas y resumen del día.",
                }
            return {"action": "charla", "response": "¡Aquí estoy contigo! ¿En qué nos enfocamos hoy?"}
