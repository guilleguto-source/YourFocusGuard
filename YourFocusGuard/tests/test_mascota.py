"""Pruebas de la mascota agente (v0.3.0): temas, mapeo y degradación."""
from __future__ import annotations

import sys

import pytest

from yourfocusguard.constants import Estado
from yourfocusguard.mascota import TEMAS, Mascota, _ESTADO_A_SPRITE

CLAVES_TEMA = {"cuerpo", "tinta", "placa", "realce", "clave"}


def test_temas_completos_y_no_blancos():
    assert set(TEMAS) == {"clasico", "oscuro", "calido"}
    for nombre, tema in TEMAS.items():
        assert set(tema) == CLAVES_TEMA, nombre
        # nunca blanco puro (pedido de la usuaria) ni negro duro
        assert tema["cuerpo"].lower() not in ("#ffffff", "#fff", "#000000")
        assert tema["clave"] != tema["cuerpo"]  # el fondo no se come al cuerpo


def test_mapeo_cubre_todos_los_estados():
    for estado in Estado:
        assert estado.value in _ESTADO_A_SPRITE, estado
    assert _ESTADO_A_SPRITE["DETENIDO"][0] == "dormido"
    assert _ESTADO_A_SPRITE["ESCALADA"][0] == "alerta"


def test_api_segura_sin_tkinter(cfg, monkeypatch):
    """Sin tkinter disponible, la mascota se desactiva y no rompe nada."""
    import builtins

    real_import = builtins.__import__

    def _sin_tkinter(nombre, *args, **kwargs):
        if nombre == "tkinter":
            raise ImportError("sin tkinter en este entorno")
        return real_import(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _sin_tkinter)
    m = Mascota(cfg)
    assert m.iniciar() is False
    assert m.disponible is False
    # la API del motor nunca lanza aunque no haya ventana
    m.fijar_estado("ESCALADA", "redes")
    m.al_alerta(2, "prueba")
    m.parar()


def test_fijar_estado_deduplica(cfg):
    """El mismo estado repetido no encola nada (no despierta a Tk)."""
    m = Mascota(cfg)
    m._run = lambda: None  # hilo inerte para este test
    m.fijar_estado("FOCO", "tesis")
    m.fijar_estado("FOCO", "tesis")
    m.fijar_estado("FOCO", "tesis")
    assert m._cola.qsize() == 1
    m.fijar_estado("PAUSA", "")
    assert m._cola.qsize() == 2


def test_manejar_mensaje_estado_y_alerta(cfg):
    """_manejar traduce estados y muestra la burbuja sin Tk real."""
    m = Mascota(cfg)

    dibujos = []
    burbujas = []
    m._dibujar = lambda sprite, texto: dibujos.append((sprite, texto))
    m._burbuja = lambda texto: burbujas.append(texto)

    m._manejar(("estado", "ESCALADA", "redes"))
    assert dibujos[-1][0] == "alerta"
    m._manejar(("alerta", 2, "vuelve a la tarea"))
    assert burbujas == ["vuelve a la tarea"]
    assert dibujos[-1][0] == "alerta"
    m._manejar(("estado", "PAUSA", ""))
    assert dibujos[-1][0] == "pausa"


@pytest.mark.skipif(sys.platform == "win32", reason="en Windows la mascota real abre ventana")
def test_run_sin_escritorio_degrada(cfg):
    """En Linux sin X (o sin tkinter), _run vuelve sin ventana y sin lanzar."""
    m = Mascota(cfg)
    m._run()  # directo, sin hilo: debe volver y dejar disponible=False
    assert m.disponible is False
