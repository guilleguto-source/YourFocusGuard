"""Pruebas del parseo del JSON de veredicto (contrato prompt v1)."""
from __future__ import annotations

import json

import pytest

from yourfocusguard.brain.parsing import InvalidVerdictJson, parse_verdict_json

JSON_OK = {
    "continuidad": False,
    "desvio": True,
    "motivo": "redes",
    "app_detectada": "chrome",
    "confianza": 0.9,
    "accion_sugerida": "toast",
}


def test_json_valido():
    v = parse_verdict_json(json.dumps(JSON_OK), "nube:gemini")
    assert v.desvio and not v.continuidad
    assert v.motivo == "redes"
    assert v.confianza == 0.9
    assert v.accion_sugerida == "toast"
    assert v.origen == "nube:gemini"


def test_json_con_vallas_markdown():
    texto = "```json\n" + json.dumps(JSON_OK) + "\n```"
    v = parse_verdict_json(texto, "nube:openai")
    assert v.desvio


def test_json_invalido():
    with pytest.raises(InvalidVerdictJson):
        parse_verdict_json("esto no es json", "nube:gemini")


def test_faltan_claves_obligatorias():
    data = {"continuidad": True}
    with pytest.raises(InvalidVerdictJson, match="faltan claves"):
        parse_verdict_json(json.dumps(data), "nube:gemini")


def test_respuesta_vacia():
    with pytest.raises(InvalidVerdictJson):
        parse_verdict_json("", "nube:gemini")
    with pytest.raises(InvalidVerdictJson):
        parse_verdict_json(None, "nube:gemini")


def test_confianza_se_acota():
    data = dict(JSON_OK, confianza=1.7)
    assert parse_verdict_json(json.dumps(data), "x").confianza == 1.0
    data = dict(JSON_OK, confianza=-3)
    assert parse_verdict_json(json.dumps(data), "x").confianza == 0.0


def test_motivo_desconocido_cae_a_otro():
    data = dict(JSON_OK, motivo="zapping")
    assert parse_verdict_json(json.dumps(data), "x").motivo == "otro"


def test_accion_desconocida_cae_a_nada():
    data = dict(JSON_OK, accion_sugerida="gritar")
    assert parse_verdict_json(json.dumps(data), "x").accion_sugerida == "nada"


def test_continuidad_por_defecto_si_falta():
    data = {"desvio": False, "confianza": 0.8}
    v = parse_verdict_json(json.dumps(data), "x")
    assert v.continuidad and not v.desvio


def test_user_prompt_lleva_tarea_e_historial():
    from yourfocusguard.brain.prompts import build_user_prompt

    texto = build_user_prompt(
        tarea="Escribir tesis cap 3",
        app_activa="pycharm",
        marcas_temporales=["14:30:00", "14:31:00"],
        historial=["14:30:00 | pycharm | tesis | continuidad (0.75)"],
    )
    assert "Escribir tesis cap 3" in texto
    assert "pycharm" in texto
    assert "14:30:00" in texto
    assert "sin tarea declarada" in build_user_prompt("", None, [], [])
