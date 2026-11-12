"""Pruebas de la memoria FIFO (5 frames, solo RAM)."""
from __future__ import annotations

from yourfocusguard.brain.base import Verdict
from yourfocusguard.memory.fifo import FrameBuffer
from yourfocusguard.memory.models import FrameSnapshot


def _snap(ts, app="chrome", title="inicio", jpeg=b"x"):
    return FrameSnapshot(ts=ts, app=app, title=title, idle_seconds=1.0, jpeg=jpeg)


def test_maxlen_expulsa_al_mas_viejo():
    fifo = FrameBuffer(5)
    for i in range(7):
        fifo.push(_snap(ts=float(i)))
    assert len(fifo) == 5
    assert fifo[0].ts == 2.0      # el frame 0 y 1 fueron expulsados
    assert fifo.latest().ts == 6.0


def test_previous_devuelve_el_anterior():
    fifo = FrameBuffer(5)
    fifo.push(_snap(1.0))
    assert fifo.previous() is None
    fifo.push(_snap(2.0))
    assert fifo.previous().ts == 1.0


def test_sample_images_extremos():
    fifo = FrameBuffer(5)
    for i in range(5):
        fifo.push(_snap(ts=float(i), jpeg=f"j{i}".encode()))
    muestras = fifo.sample_images(2)
    assert len(muestras) == 2
    assert muestras[0][1] == b"j0"     # la más antigua
    assert muestras[-1][1] == b"j4"    # la actual


def test_sample_images_menos_frames_que_pedidos():
    fifo = FrameBuffer(5)
    fifo.push(_snap(1.0, jpeg=b"a"))
    assert fifo.sample_images(2) == [(1.0, b"a")]


def test_history_lines_incluye_veredicto():
    fifo = FrameBuffer(5)
    snap = _snap(1_000_000.0, app="pycharm", title="tesis — cap 3")
    snap.verdict = Verdict(
        continuidad=True, desvio=False, motivo="ninguno", app_detectada="pycharm",
        confianza=0.75, accion_sugerida="nada", origen="heuristica",
    )
    fifo.push(snap)
    linea = fifo.history_lines()[0]
    assert "pycharm" in linea
    assert "continuidad" in linea
    assert "0.75" in linea
