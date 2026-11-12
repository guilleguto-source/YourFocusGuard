"""Pruebas de robustez y resiliencia de la cadena de voz Groq (v0.8.4).

Verifica la lista de modelos oficiales vivos, el filtro de alucinaciones de silencio,
la rotación ante errores HTTP 404/410/429 y los mensajes honestos de fallo.
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from yourfocusguard import __version__
from yourfocusguard.actions.groq_voice import (
    MODELOS_LLM,
    USER_AGENT,
    conversar_con_muse,
    es_transcripcion_valida,
    transcribir_con_groq,
)


def test_version_es_084():
    assert __version__ == "0.8.4"


def test_modelos_llm_oficiales_vivos():
    """Garantiza que la cadena contenga modelos de producción y no los decomisionados."""
    assert "llama-3.3-70b-versatile" not in MODELOS_LLM
    assert "llama-3.1-8b-instant" not in MODELOS_LLM
    assert "qwen/qwen3.8-27b" in MODELOS_LLM
    assert "openai/gpt-oss-120b" in MODELOS_LLM
    assert "openai/gpt-oss-20b" in MODELOS_LLM


def test_user_agent_evita_bloqueo():
    assert "Mozilla/5.0" in USER_AGENT
    assert "YourFocusGuard/0.8.4" in USER_AGENT


def test_es_transcripcion_valida_filtra_alucinaciones_silencio():
    assert es_transcripcion_valida("Gracias.") is False
    assert es_transcripcion_valida("¡gracias!") is False
    assert es_transcripcion_valida("Thank you.") is False
    assert es_transcripcion_valida("Subtítulos por la comunidad") is False
    assert es_transcripcion_valida("") is False
    assert es_transcripcion_valida("   ") is False


def test_es_transcripcion_valida_preserva_comandos_reales():
    assert es_transcripcion_valida("pausa") is True
    assert es_transcripcion_valida("sí") is True
    assert es_transcripcion_valida("no") is True
    assert es_transcripcion_valida("ok") is True
    assert es_transcripcion_valida("hola") is True
    assert es_transcripcion_valida("agenda reunión con el cliente") is True
    assert es_transcripcion_valida("pon música de concentración") is True


def test_transcribir_con_groq_vacia_alucinacion_silencio():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"text": "Gracias."}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("yourfocusguard.actions.groq_voice.obtener_api_key_groq", return_value="gsk_test"), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = transcribir_con_groq(b"RIFFdummydata" * 20)
        assert res == ""


def test_conversar_con_muse_rota_ante_410_y_429():
    """Si el primer modelo da 410 (gone) o 429 (rate limit), debe intentar con el siguiente."""
    resp_exitosa = MagicMock()
    resp_exitosa.read.return_value = json.dumps({
        "choices": [{"message": {"content": "¡Hola! Todo listo."}}],
        "usage": {"total_tokens": 10}
    }).encode("utf-8")
    resp_exitosa.__enter__.return_value = resp_exitosa

    # Primer intento 410, segundo intento 200 OK
    intentos = [
        urllib.error.HTTPError("url", 410, "Gone", {}, None),
        resp_exitosa,
    ]

    with patch("yourfocusguard.actions.groq_voice.obtener_api_key_groq", return_value="gsk_test"), \
         patch("yourfocusguard.actions.groq_voice.obtener_endpoint_llm_local", return_value=None), \
         patch("urllib.request.urlopen", side_effect=intentos):
        res = conversar_con_muse("hola einstein")
        assert res == "¡Hola! Todo listo."


def test_conversar_con_muse_mensaje_honesto_tras_fallo_completo():
    """Garantiza que no dé falso positivo de éxito si todos los modelos fallan."""
    err_404 = urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    with patch("yourfocusguard.actions.groq_voice.obtener_api_key_groq", return_value="gsk_test"), \
         patch("yourfocusguard.actions.groq_voice.obtener_endpoint_llm_local", return_value=None), \
         patch("urllib.request.urlopen", side_effect=err_404):
        res = conversar_con_muse("hola einstein")
        assert "No pude conectar con mi cabeza en la nube" in res
        assert "Sigamos con energía" not in res


def test_conversar_con_muse_401_aborta_sin_reintentos_inutiles():
    """Un 401 (token inválido) no debe quemar tiempo probando los demás modelos."""
    err_401 = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

    with patch("yourfocusguard.actions.groq_voice.obtener_api_key_groq", return_value="gsk_invalido"), \
         patch("yourfocusguard.actions.groq_voice.obtener_endpoint_llm_local", return_value=None), \
         patch("urllib.request.urlopen", side_effect=err_401) as mock_url:
        res = conversar_con_muse("hola")
        assert mock_url.call_count == 1
        assert "No pude conectar con mi cabeza en la nube" in res
