"""Pruebas de las acciones sobre ventanas (v0.3.0)."""
from __future__ import annotations

import sys

import pytest

from yourfocusguard.actions import window_actions as wa


# --------------------------------------------------------------------------- #
# Matcher puro (corre en cualquier SO)
# --------------------------------------------------------------------------- #

def test_matchea_por_proceso():
    assert wa.matchea("lightroom", "lightroomclassic", "catálogo 2024")
    assert wa.matchea("Light.?room", "lightroom", "")
    assert not wa.matchea("lightroom", "explorer", "Este equipo")


def test_matchea_por_titulo():
    # YouTube en el navegador: matchea el título aunque el proceso sea chrome
    assert wa.matchea("youtube", "chrome", "YouTube - gatitos")
    assert not wa.matchea("youtube", "chrome", "documentación de Python")


def test_matchea_insensible_y_regex_invalida():
    assert wa.matchea("YOUTUBE", "chrome", "youtube música")
    # regex inválido se trata como literal: nunca rompe
    assert wa.matchea("a[", "proceso a[", None)
    assert not wa.matchea("a[", "otro", "título")


def test_matchea_none():
    assert not wa.matchea("youtube", None, None)
    assert not wa.matchea("", "chrome", "YouTube")


# --------------------------------------------------------------------------- #
# Degradación fuera de Windows (en Windows real se prueban a mano)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform == "win32", reason="en Windows abre ventanas reales")
def test_fuera_de_windows_degradan():
    assert wa.traer_al_frente("lightroom") is None
    assert wa.traer_al_frente("") is None
    assert wa.minimizar_primera_plano() is False
