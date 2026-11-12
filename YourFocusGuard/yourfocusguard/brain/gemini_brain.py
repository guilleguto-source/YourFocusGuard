"""Nivel A, proveedor Gemini: SDK oficial google-genai.

El cliente se crea perezosamente: si no hay librería o no hay clave, el
router lo traduce en modo local sin detener el agente. Temperatura 0 y
modo de salida JSON estricto, con reintento único (Apéndice B).
"""
from __future__ import annotations

import logging
import os
import time

from yourfocusguard.brain.base import Brain, BrainUnavailableError, Verdict
from yourfocusguard.brain.parsing import InvalidVerdictJson, parse_verdict_json
from yourfocusguard.brain.prompts import SYSTEM_PROMPT_V1, build_user_prompt
from yourfocusguard.config import Config
from yourfocusguard.constants import ORIGEN_GEMINI
from yourfocusguard.memory.fifo import FrameBuffer

log = logging.getLogger(__name__)


class GeminiBrain(Brain):
    name = "gemini"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise BrainUnavailableError(
                "falta GEMINI_API_KEY: cópiala en .env (ver README)"
            )
        try:
            from google import genai
        except ImportError as exc:
            raise BrainUnavailableError(f"librería google-genai no instalada: {exc}") from exc
        self._client = genai.Client(api_key=api_key)

    def analyze(self, buffer: FrameBuffer, tarea: str = "") -> Verdict:
        self._ensure_client()
        ultimo = buffer.latest()
        if ultimo is None:
            raise BrainUnavailableError("la FIFO está vacía")

        imagenes = buffer.sample_images(self.cfg.cerebro.imagenes_por_analisis)
        if not imagenes:
            raise BrainUnavailableError("no hay imágenes en la FIFO")

        marcas = [time.strftime("%H:%M:%S", time.localtime(ts)) for ts, _ in imagenes]
        texto_usuario = build_user_prompt(
            tarea, ultimo.app, marcas, buffer.history_lines()
        )

        ultimo_error: Exception | None = None
        for intento in (1, 2):  # reintento único ante JSON inválido
            try:
                from google.genai import types

                contenido: list = [texto_usuario]
                contenido += [
                    types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")
                    for _, jpeg in imagenes
                ]
                config = types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT_V1,
                    temperature=self.cfg.cerebro.temperatura,
                    response_mime_type="application/json",
                )
                respuesta = self._client.models.generate_content(
                    model=self.cfg.cerebro.modelo_gemini,
                    contents=contenido,
                    config=config,
                )
                return parse_verdict_json(
                    respuesta.text, ORIGEN_GEMINI, ts=ultimo.ts
                )
            except InvalidVerdictJson as exc:
                ultimo_error = exc
                log.warning("gemini: JSON inválido (intento %d): %s", intento, exc)
                continue
            except BrainUnavailableError:
                raise
            except Exception as exc:  # red, cuota, clave, seguridad...
                raise BrainUnavailableError(f"gemini: {exc}") from exc

        raise BrainUnavailableError(
            f"gemini: JSON inválido tras el reintento ({ultimo_error})"
        )
