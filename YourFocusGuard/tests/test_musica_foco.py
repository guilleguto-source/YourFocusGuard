"""Pruebas unitarias para el controlador de música de foco (v0.8.3 Fase 4)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from yourfocusguard.actions.musica_foco import (
    ajustar_volumen,
    detener_musica_foco,
    es_intencion_detener_musica,
    es_intencion_musica,
    estado_musica,
    generar_ruido_marron,
    iniciar_musica_foco,
)
from yourfocusguard.config import MusicaCfg


def test_es_intencion_musica():
    assert es_intencion_musica("pon música de concentración") is True
    assert es_intencion_musica("activar ruido marrón") is True
    assert es_intencion_musica("para la música por favor") is True
    assert es_intencion_musica("sube el volumen") is True
    assert es_intencion_musica("cuál es la capital de Francia") is False
    assert es_intencion_musica("") is False


def test_es_intencion_detener_musica():
    assert es_intencion_detener_musica("para la música") is True
    assert es_intencion_detener_musica("silencio") is True
    assert es_intencion_detener_musica("detener el sonido") is True
    assert es_intencion_detener_musica("pon música") is False


def test_generar_ruido_marron_array():
    arr = generar_ruido_marron(duracion_seg=0.5, sample_rate=1000)
    assert isinstance(arr, np.ndarray)
    assert arr.ndim == 2
    assert arr.shape == (500, 2)
    assert arr.dtype == np.int16


def test_iniciar_musica_deshabilitada():
    cfg = MusicaCfg(habilitado=False)
    ok, msg = iniciar_musica_foco(cfg=cfg)
    assert ok is False
    assert "desactivada" in msg


def test_iniciar_y_detener_con_mock():
    mock_channel = MagicMock()
    mock_sound = MagicMock()

    with patch("yourfocusguard.actions.musica_foco._asegurar_mixer", return_value=True), \
         patch("pygame.mixer.Channel", return_value=mock_channel), \
         patch("pygame.sndarray.make_sound", return_value=mock_sound), \
         patch("pygame.mixer.get_init", return_value=True):

        ok, msg = iniciar_musica_foco(tipo="marron", volumen=0.6)
        assert ok is True
        assert "ruido marrón" in msg
        mock_channel.play.assert_called_once_with(mock_sound, loops=-1)
        mock_channel.set_volume.assert_called_with(0.6)

        st = estado_musica()
        assert st["activo"] is True
        assert st["tipo"] == "marron"

        # Ajustar volumen
        ok_v, _ = ajustar_volumen(0.8)
        assert ok_v is True
        mock_channel.set_volume.assert_called_with(0.8)

        # Detener
        ok_d, msg_d = detener_musica_foco()
        assert ok_d is True
        mock_channel.stop.assert_called_once()
        assert estado_musica()["activo"] is False
