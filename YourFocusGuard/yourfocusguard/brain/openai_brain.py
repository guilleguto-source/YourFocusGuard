"""Nivel A, proveedor OpenAI: gpt-4o-mini vía SDK oficial.

Mismo contrato que Gemini: temperatura 0, salida JSON estricta
(``response_format``) y reintento único ante JSON inválido.
"""
from __future__ import annotations

import base64
import logging
import os
import time

from yourfocusguard.brain.base import Brain, BrainUnavailableError, Verdict
from yourfocusguard.brain.parsing import InvalidVerdictJson, parse_verdict_json
from yourfocusguard.brain.prompts import SYSTEM_PROMPT_V1, build_user_prompt
from yourfocusguard.config import Config
from yourfocusguard.constants import ORIGEN_OPENAI
from yourfocusguard.memory.fifo import FrameBuffer

log = logging.getLogger(__name__)


class OpenAIBrain(Brain):
    name = "openai"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise BrainUnavailableError(
                "falta OPENAI_API_KEY: cópiala en .env (ver README)"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise BrainUnavailableError(f"librería openai no instalada: {exc}") from exc
        self._client = OpenAI(api_key=api_key)

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

        contenido: list[dict] = [{"type": "text", "text": texto_usuario}]
        for _, jpeg in imagenes:
            b64 = base64.b64encode(jpeg).decode("ascii")
            contenido.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "low",  # ahorro de tokens (cap. 4 del blueprint)
                    },
                }
            )

        ultimo_error: Exception | None = None
        for intento in (1, 2):
            try:
                respuesta = self._client.chat.completions.create(
                    model=self.cfg.cerebro.modelo_openai,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_V1},
                        {"role": "user", "content": contenido},
                    ],
                    temperature=self.cfg.cerebro.temperatura,
                    max_tokens=200,
                    response_format={"type": "json_object"},
                )
                texto = respuesta.choices[0].message.content
                return parse_verdict_json(texto, ORIGEN_OPENAI, ts=ultimo.ts)
            except InvalidVerdictJson as exc:
                ultimo_error = exc
                log.warning("openai: JSON inválido (intento %d): %s", intento, exc)
                continue
            except BrainUnavailableError:
                raise
            except Exception as exc:
                raise BrainUnavailableError(f"openai: {exc}") from exc

        raise BrainUnavailableError(
            f"openai: JSON inválido tras el reintento ({ultimo_error})"
        )
