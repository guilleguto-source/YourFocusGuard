"""Pruebas de la lista de exclusiones de privacidad (cap. 7)."""
from __future__ import annotations

from yourfocusguard.privacy.exclusions import Exclusiones

APPS = ["keepass", "bitwarden", "1password"]
TITULOS = [
    "inprivate", "incognito", "incógnito", "privad[oa]", "banca", "banco",
    "home banking", "mercado ?pago", "afip",
]


def _ex():
    return Exclusiones(APPS, TITULOS)


def test_app_excluida():
    assert _ex().excluida("keepass", "KeePass - mi bóveda") == "app:keepass"


def test_titulo_excluido_regex():
    excl = _ex()
    assert excl.excluida("chrome", "Home Banking - Banco Nación") is not None
    assert excl.excluida("chrome", "Mercado Pago: mi cuenta") is not None
    assert excl.excluida("msedge", "InPrivate") is not None
    assert excl.excluida("firefox", "Ventana privada") is not None


def test_ventana_normal_no_excluida():
    assert _ex().excluida("pycharm", "tesis cap 3") is None
    assert _ex().excluida(None, None) is None


def test_case_insensitive():
    assert _ex().excluida("Bitwarden", "Bóveda") is not None


def test_regex_invalida_no_rompe():
    """Un patrón mal escrito por el usuario cae a comparación literal."""
    excl = Exclusiones([], ["[inci("])
    assert excl.excluida("chrome", "algo [inci( raro") is not None
    assert excl.excluida("chrome", "normal") is None
