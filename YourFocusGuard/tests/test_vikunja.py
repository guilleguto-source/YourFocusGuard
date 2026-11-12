"""Pruebas unitarias para la integración con Vikunja (v0.8.3 Fase 4)."""
from __future__ import annotations

import io
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from yourfocusguard.config import VikunjaCfg
from yourfocusguard.integrations.vikunja import (
    crear_tarea,
    es_intencion_agenda,
    limpiar_texto_agenda,
)


def test_es_intencion_agenda():
    assert es_intencion_agenda("agenda reunión de diseño mañana") is True
    assert es_intencion_agenda("crear tarea comprar café") is True
    assert es_intencion_agenda("agrega una nueva tarea para el viernes") is True
    assert es_intencion_agenda("guardar en vikunja revisar informe") is True
    assert es_intencion_agenda("hola einstein cómo estás hoy") is False
    assert es_intencion_agenda("") is False


def test_limpiar_texto_agenda():
    assert limpiar_texto_agenda("agenda la tarea de enviar reporte") == "enviar reporte"
    assert limpiar_texto_agenda("crear tarea comprar café") == "comprar café"
    assert limpiar_texto_agenda("en vikunja revisar servidor") == "revisar servidor"


def test_crear_tarea_deshabilitada_o_sin_credenciales():
    cfg_deshabilitada = VikunjaCfg(habilitado=False)
    ok, msg = crear_tarea("revisar correo", cfg=cfg_deshabilitada)
    assert ok is False
    assert "no está habilitado" in msg

    cfg_sin_token = VikunjaCfg(habilitado=True, url="http://localhost:3456", token="")
    ok, msg = crear_tarea("revisar correo", cfg=cfg_sin_token)
    assert ok is False
    assert "no tiene URL o token" in msg


def test_crear_tarea_exitosa():
    cfg = VikunjaCfg(habilitado=True, url="http://localhost:3456", token="tk_test123", proyecto_defecto_id=2)

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 201
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        ok, msg = crear_tarea("comprar café", due_date_iso="2026-11-10T15:00:00Z", cfg=cfg)
        assert ok is True
        assert "Tarea agendada en Vikunja" in msg
        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        assert req.get_full_url() == "http://localhost:3456/api/v1/projects/2/tasks"
        assert req.get_method() == "PUT"
        assert req.headers["Authorization"] == "Bearer tk_test123"


def test_crear_tarea_errores_red():
    cfg = VikunjaCfg(habilitado=True, url="http://localhost:3456", token="tk_test123")

    # Error HTTP 401
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)):
        ok, msg = crear_tarea("comprar pan", cfg=cfg)
        assert ok is False
        assert "HTTP 401" in msg

    # Error Conexión / URLError
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        ok, msg = crear_tarea("comprar pan", cfg=cfg)
        assert ok is False
        assert "no alcanzable" in msg
