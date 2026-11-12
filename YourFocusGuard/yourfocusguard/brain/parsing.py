"""Parseo y validación del JSON de veredicto (contrato del prompt v1).

El blueprint exige salida JSON estricta validada (tabla 11): un JSON inválido
provoca un único reintento en el adaptador y, si persiste, la degradación al
Nivel B. Nunca una excepción sin controlar.
"""
from __future__ import annotations

import json
import re

from yourfocusguard.brain.base import Verdict

_MOTIVOS = {"redes", "video", "celular", "conversacion", "mirada", "otro", "ninguno"}
_ACCIONES = {"nada", "mascota", "aviso", "toast", "voz"}


class InvalidVerdictJson(ValueError):
    """El modelo respondió algo que no valida contra el esquema del prompt v1."""


def _sin_vallas(texto: str) -> str:
    """Quita las vallas de código markdown que a veces añaden los modelos."""
    texto = texto.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if m:
        return m.group(1)
    return texto


def parse_verdict_json(texto: str | None, origen: str, ts: float = 0.0) -> Verdict:
    """Convierte la respuesta del modelo en un Verdict validado."""
    if not texto or not texto.strip():
        raise InvalidVerdictJson("respuesta vacía")

    try:
        data = json.loads(_sin_vallas(texto))
    except json.JSONDecodeError as exc:
        raise InvalidVerdictJson(f"JSON inválido: {exc}") from exc

    if not isinstance(data, dict):
        raise InvalidVerdictJson("la respuesta no es un objeto")

    faltan = {"desvio", "confianza"} - set(data)
    if faltan:
        raise InvalidVerdictJson(f"faltan claves: {sorted(faltan)}")

    motivo = str(data.get("motivo", "otro")).strip().lower()
    if motivo not in _MOTIVOS:
        motivo = "otro"
    accion = str(data.get("accion_sugerida", "nada")).strip().lower()
    if accion not in _ACCIONES:
        accion = "nada"

    try:
        confianza = float(data.get("confianza", 0.0))
    except (TypeError, ValueError):
        raise InvalidVerdictJson("confianza no es numérica") from None
    confianza = max(0.0, min(1.0, confianza))

    return Verdict(
        continuidad=bool(data.get("continuidad", not data.get("desvio", False))),
        desvio=bool(data.get("desvio", False)),
        motivo=motivo,
        app_detectada=str(data.get("app_detectada", ""))[:120],
        confianza=confianza,
        accion_sugerida=accion,
        origen=origen,
        ts=ts,
    )
