"""Pruebas del router: cadencia, caché, presupuesto, disyuntor y degradación."""
from __future__ import annotations

import pytest

from yourfocusguard.brain.base import Brain, BrainUnavailableError, Verdict
from yourfocusguard.brain.heuristic import HeuristicBrain
from yourfocusguard.brain.router import BrainRouter
from yourfocusguard.memory.fifo import FrameBuffer
from yourfocusguard.memory.models import FrameSnapshot
from yourfocusguard.storage.db import EventDB


class RelojFalso:
    def __init__(self, t0=1_000_000.0):
        self.t = t0

    def __call__(self):
        return self.t

    def avanzar(self, seg):
        self.t += seg


class CerebroFalso(Brain):
    name = "falso"

    def __init__(self, veredicto=None, error=None):
        self.veredicto = veredicto
        self.error = error
        self.llamadas = 0

    def analyze(self, buffer, tarea=""):
        self.llamadas += 1
        if self.error:
            raise BrainUnavailableError(self.error)
        return self.veredicto


def _v(desvio=False, conf=0.9, origen="nube:falso"):
    return Verdict(
        continuidad=not desvio, desvio=desvio, motivo="video" if desvio else "ninguno",
        app_detectada="chrome", confianza=conf, accion_sugerida="nada",
        origen=origen, ts=0.0,
    )


def _buffer_con_frame(cfg, app="chrome", title="YouTube"):
    fifo = FrameBuffer(cfg.captura.fifo_frames)
    fifo.push(FrameSnapshot(ts=1_000_000.0, app=app, title=title, jpeg=b"jpg"))
    return fifo


def test_sin_nube_siempre_heuristica(cfg):
    router = BrainRouter(cfg)
    fifo = _buffer_con_frame(cfg)
    v = router.analyze(fifo)
    assert v.origen == "heuristica"


def test_modo_privado_apaga_la_nube(cfg):
    cfg.modo_privado = True
    cloud = CerebroFalso(_v())
    router = BrainRouter(cfg, cloud=cloud)
    router.analyze(_buffer_con_frame(cfg))
    assert cloud.llamadas == 0


def test_nube_disponible_se_usa(cfg):
    cloud = CerebroFalso(_v())
    router = BrainRouter(cfg, cloud=cloud)
    v = router.analyze(_buffer_con_frame(cfg))
    assert cloud.llamadas == 1
    assert v.origen == "nube:falso"


def test_cadencia_entre_ciclos(cfg):
    """Entre análisis de nube, la heurística es gratis (cap. 3-4)."""
    reloj = RelojFalso()
    cloud = CerebroFalso(_v())
    router = BrainRouter(cfg, cloud=cloud, reloj=reloj)

    assert router.analyze(_buffer_con_frame(cfg, app="pycharm", title="tesis t1")).origen == "nube:falso"
    reloj.avanzar(30)  # < 60 s: no toca la nube
    assert router.analyze(_buffer_con_frame(cfg, app="pycharm", title="tesis t1")).origen == "heuristica"
    reloj.avanzar(31)  # 61 s desde la última: vuelve a la nube (ventana distinta: sin caché)
    assert router.analyze(_buffer_con_frame(cfg, app="chrome", title="YouTube")).origen == "nube:falso"
    assert cloud.llamadas == 2


def test_cache_misma_ventana_continuidad(cfg):
    reloj = RelojFalso()
    cloud = CerebroFalso(_v(desvio=False))
    router = BrainRouter(cfg, cloud=cloud, reloj=reloj)
    fifo = _buffer_con_frame(cfg, app="pycharm", title="tesis cap 3")

    router.analyze(fifo)
    reloj.avanzar(cfg.cerebro.analisis_nube_seg + 1)  # cadencia cumplida
    v = router.analyze(fifo)
    assert v.origen == "cache"
    assert cloud.llamadas == 1  # no gastó otra llamada


def test_cache_no_aplica_a_desvios(cfg):
    """Un desvío no se cachea: la situación sigue evolucionando."""
    reloj = RelojFalso()
    cloud = CerebroFalso(_v(desvio=True))
    router = BrainRouter(cfg, cloud=cloud, reloj=reloj)
    fifo = _buffer_con_frame(cfg, app="chrome", title="YouTube")

    router.analyze(fifo)
    reloj.avanzar(cfg.cerebro.analisis_nube_seg + 1)
    assert router.analyze(fifo).origen == "nube:falso"
    assert cloud.llamadas == 2


def test_cache_caduca(cfg):
    reloj = RelojFalso()
    cloud = CerebroFalso(_v())
    router = BrainRouter(cfg, cloud=cloud, reloj=reloj)
    fifo = _buffer_con_frame(cfg, app="pycharm", title="tesis")

    router.analyze(fifo)
    reloj.avanzar(cfg.cerebro.analisis_nube_seg + 1 + cfg.cerebro.cache_min_seg * 60)
    assert router.analyze(fifo).origen == "nube:falso"
    assert cloud.llamadas == 2


def test_fallo_puntual_degrada_a_b(cfg):
    eventos = []
    reloj = RelojFalso()
    cloud = CerebroFalso(error="sin red")
    router = BrainRouter(cfg, cloud=cloud, on_event=lambda t, m: eventos.append((t, m)), reloj=reloj)
    v = router.analyze(_buffer_con_frame(cfg, app="pycharm", title="tesis"))
    assert v.origen == "heuristica"
    assert ("cerebro", "fallback:falso") in eventos


def test_disyuntor_se_abre_y_se_recupera(cfg):
    eventos = []
    reloj = RelojFalso()
    cloud = CerebroFalso(error="500")
    router = BrainRouter(
        cfg, cloud=cloud, on_event=lambda t, m: eventos.append((t, m)), reloj=reloj
    )
    fifo = _buffer_con_frame(cfg, app="chrome", title="YouTube")

    for _ in range(3):  # tres fallos consecutivos abren el disyuntor
        router.analyze(fifo)
        reloj.avanzar(cfg.cerebro.analisis_nube_seg + 1)
    assert ("cerebro", "disyuntor_abierto:falso") in eventos

    llamadas_antes = cloud.llamadas
    router.analyze(fifo)  # disyuntor abierto: ni llama
    assert cloud.llamadas == llamadas_antes

    reloj.avanzar(cfg.cerebro.disyuntor_descanso_min * 60 + 1)  # media apertura
    cloud.error = None
    cloud.veredicto = _v()
    v = router.analyze(fifo)
    assert v.origen == "nube:falso"  # recuperada


def test_presupuesto_diario_con_corte(cfg, tmp_path):
    db = EventDB(tmp_path / "d" / "base.db")
    cfg.cerebro.coste_por_analisis_usd = 0.40
    cfg.cerebro.presupuesto_diario_usd = 0.75
    eventos = []
    reloj = RelojFalso()
    cloud = CerebroFalso(_v())
    router = BrainRouter(
        cfg, cloud=cloud, presupuesto=db,
        on_event=lambda t, m: eventos.append((t, m)), reloj=reloj,
    )
    fifo = _buffer_con_frame(cfg)

    v1 = router.analyze(_buffer_con_frame(cfg, app="pycharm", title="tesis t1"))
    reloj.avanzar(61)
    v2 = router.analyze(_buffer_con_frame(cfg, app="pycharm", title="tesis t2"))
    reloj.avanzar(61)
    assert v1.origen == v2.origen == "nube:falso"
    assert abs(db.presupuesto_hoy() - 0.80) < 1e-9

    v3 = router.analyze(_buffer_con_frame(cfg, app="pycharm", title="tesis t3"))  # corte
    assert v3.origen == "heuristica"
    assert ("cerebro", "presupuesto_agotado") in eventos
    assert cloud.llamadas == 2
    db.cerrar()


def test_veredicto_debil_de_la_nube_pasa_tal_cual(cfg):
    """La nube puede dudar (confianza baja): el veredicto viaja igual."""
    cloud = CerebroFalso(_v(desvio=True, conf=0.4))
    router = BrainRouter(cfg, cloud=cloud)
    v = router.analyze(_buffer_con_frame(cfg))
    assert v.confianza == 0.4 and v.desvio
    assert not v.autoritario
