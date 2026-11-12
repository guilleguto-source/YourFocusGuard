"""Pruebas del Nivel B: heurística local (app + título + continuidad)."""
from __future__ import annotations

from yourfocusguard.brain.heuristic import HeuristicBrain
from yourfocusguard.memory.fifo import FrameBuffer
from yourfocusguard.memory.models import FrameSnapshot


def _buffer(cfg, pasos):
    """pasos = [(app, titulo), ...] -> FrameBuffer con esos frames."""
    fifo = FrameBuffer(cfg.captura.fifo_frames)
    for i, (app, titulo) in enumerate(pasos):
        fifo.push(FrameSnapshot(ts=1_000_000.0 + i * 15, app=app, title=titulo))
    return fifo


def test_dos_frames_distraccion_video(cfg):
    brain = HeuristicBrain(cfg)
    fifo = _buffer(cfg, [("chrome", "YouTube"), ("chrome", "gatitos en YouTube")])
    v = brain.analyze(fifo)
    assert v.desvio and v.confianza == 0.85
    assert v.motivo == "video"


def test_un_solo_frame_distraccion_es_debil(cfg):
    """Regla 1: una transición breve no cuenta (confianza < 0.6)."""
    brain = HeuristicBrain(cfg)
    fifo = _buffer(cfg, [("pycharm", "tesis"), ("chrome", "YouTube")])
    v = brain.analyze(fifo)
    assert v.desvio and v.confianza == 0.55
    assert not v.autoritario


def test_distraccion_por_redes(cfg):
    brain = HeuristicBrain(cfg)
    fifo = _buffer(cfg, [("chrome", "tiktok"), ("chrome", "tiktok - para ti")])
    v = brain.analyze(fifo)
    assert v.desvio and v.motivo == "redes"


def test_regex_x_com(cfg):
    brain = HeuristicBrain(cfg)
    fifo = _buffer(cfg, [("chrome", "Inicio / x.com"), ("chrome", "x.com (antes Twitter)")])
    v = brain.analyze(fifo)
    assert v.desvio and v.motivo == "redes"


def test_app_enfoque(cfg):
    brain = HeuristicBrain(cfg)
    fifo = _buffer(cfg, [("pycharm", "blueprint.py"), ("pycharm", "tesis.docx")])
    v = brain.analyze(fifo)
    assert not v.desvio and v.confianza == 0.75


def test_titulo_enfoque_regex(cfg):
    cfg.heuristica.titulos_enfoque = ["tesis", "cap[íi]tulo"]
    brain = HeuristicBrain(cfg)
    fifo = _buffer(cfg, [("firefox", "Capítulo 3 — Google Docs"), ("firefox", "docs tesis")])
    v = brain.analyze(fifo)
    assert not v.desvio and v.confianza == 0.75


def test_neutra_y_desconocida_son_debiles(cfg):
    brain = HeuristicBrain(cfg)
    v = HeuristicBrain(cfg).analyze(_buffer(cfg, [("explorer", "Este equipo")]))
    assert not v.desvio and v.confianza == 0.35
    v2 = brain.analyze(_buffer(cfg, [("appraradecona", "título raro")]))
    assert not v2.desvio and v2.confianza == 0.25


def test_fifo_vacia_devuelve_confianza_cero(cfg):
    brain = HeuristicBrain(cfg)
    v = brain.analyze(FrameBuffer(5))
    assert v.confianza == 0.0 and not v.desvio


def test_llamadas_no_son_distraccion(cfg):
    """Regla 3: zoom/teams quedan como neutras (trabajo), no como desvío."""
    cfg.heuristica.apps_neutras = cfg.heuristica.apps_neutras + ["zoom", "ms-teams"]
    brain = HeuristicBrain(cfg)
    fifo = _buffer(cfg, [("zoom", "Reunión de equipo"), ("zoom", "Reunión")])
    v = brain.analyze(fifo)
    assert not v.desvio
