"""Pruebas del vigilante de prohibiciones (v0.3.0): presupuestos diarios."""
from __future__ import annotations

from yourfocusguard.config import ProhibicionCfg
from yourfocusguard.storage.db import EventDB
from yourfocusguard.vigilante import VigilanteProhibiciones

T0 = 2_000_000.0


class RelojFalso:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def avanzar(self, seg):
        self.t += seg


def _cfg_con(cfg, entradas):
    cfg.prohibiciones.lista = [ProhibicionCfg(**e) for e in entradas]
    return cfg


def _montar(cfg, entradas):
    _cfg_con(cfg, entradas)
    db = EventDB(cfg.ruta_db)
    reloj = RelojFalso()
    v = VigilanteProhibiciones(cfg, db, reloj)
    v.tick(reloj.t, None, None)  # tick base: fija _ultimo_ts sin contar
    return v, db, reloj


# --------------------------------------------------------------------------- #
# Conteo y transición a presupuesto agotado
# --------------------------------------------------------------------------- #

def test_cuenta_por_titulo_con_app_neutra(cfg):
    """YouTube en el navegador: el patrón matchea el TÍTULO aunque el proceso
    sea chrome (así lo pidió la usuaria: prohibir un sitio, no una app)."""
    v, db, reloj = _montar(cfg, [{"patron": "youtube", "limite_min_dia": 60}])
    # 30 min en primer plano, en pasos de 15 s
    for _ in range(120):
        reloj.avanzar(15)
        v.tick(reloj.t, "chrome", "YouTube - gatitos")
    assert db.presupuesto_usado_hoy("youtube") == 120 * 15
    assert v.resumen()["youtube"] == 30.0
    db.cerrar()


def test_aviso_exactamente_una_vez(cfg):
    v, db, reloj = _montar(cfg, [{"patron": "youtube", "limite_min_dia": 5}])
    avisos = []
    for _ in range(30):  # 30 ticks de 15 s = 7.5 min > 5 min
        reloj.avanzar(15)
        avisos.extend(v.tick(reloj.t, "chrome", "YouTube - música"))
    assert len(avisos) == 1
    assert avisos[0].patron == "youtube"
    assert avisos[0].limite_min == 5
    db.cerrar()


def test_bloqueo_activo_debe_bloquear(cfg):
    v, db, reloj = _montar(
        cfg, [{"patron": "youtube", "limite_min_dia": 5, "bloqueo_activo": True}]
    )
    for _ in range(20):  # 5 min
        reloj.avanzar(15)
        v.tick(reloj.t, "chrome", "YouTube")
    entrada = v.debe_bloquear("chrome", "YouTube - x")
    assert entrada is not None and entrada.patron == "youtube"
    # otro sitio al frente: no se bloquea
    assert v.debe_bloquear("explorer", "Este equipo") is None
    db.cerrar()


def test_sin_bloqueo_activo_no_bloquea(cfg):
    v, db, reloj = _montar(
        cfg, [{"patron": "youtube", "limite_min_dia": 5, "bloqueo_activo": False}]
    )
    for _ in range(20):
        reloj.avanzar(15)
        v.tick(reloj.t, "chrome", "YouTube")
    assert v.debe_bloquear("chrome", "YouTube") is None
    db.cerrar()


# --------------------------------------------------------------------------- #
# Persistencia y recarga
# --------------------------------------------------------------------------- #

def test_sobrevive_reinicios_y_no_reavisa(cfg):
    v1, db, reloj = _montar(
        cfg, [{"patron": "youtube", "limite_min_dia": 5, "bloqueo_activo": True}]
    )
    for _ in range(20):
        reloj.avanzar(15)
        v1.tick(reloj.t, "chrome", "YouTube")
    db.cerrar()

    # segundo "arranque del agente": mismo db, mismo día
    v2 = VigilanteProhibiciones(cfg, EventDB(cfg.ruta_db), reloj)
    avisos = v2.tick(reloj.t, "chrome", "YouTube - más")
    assert avisos == []  # ya venía agotada de la corrida anterior: silencio
    assert v2.debe_bloquear("chrome", "YouTube") is not None  # pero bloquea
    assert v2.resumen()["youtube"] >= 5.0


def test_firma_detecta_edicion_en_vivo(cfg):
    v, db, reloj = _montar(cfg, [{"patron": "youtube", "limite_min_dia": 60}])
    for _ in range(4):  # 60 s usados
        reloj.avanzar(15)
        v.tick(reloj.t, "chrome", "YouTube")
    assert v.resumen()["youtube"] == 1.0

    # el panel sube el límite NO: lo BAJA a 1 min y enciende el bloqueo
    _cfg_con(cfg, [{"patron": "youtube", "limite_min_dia": 1, "bloqueo_activo": True}])
    for _ in range(1):  # 15 s más: 75 s >= 60 s del nuevo límite
        reloj.avanzar(15)
        v.tick(reloj.t, "chrome", "YouTube")
    assert v.debe_bloquear("chrome", "YouTube") is not None
    # 75 s usados (redondeo a 1 decimal: 1.25 -> 1.2)
    assert v.resumen()["youtube"] >= 1.2
    db.cerrar()


def test_patrones_duplicados_se_deduplican(cfg):
    _cfg_con(
        cfg,
        [
            {"patron": "youtube", "limite_min_dia": 60},
            {"patron": "YouTube", "limite_min_dia": 30},  # mismo, con mayúscula
        ],
    )
    db = EventDB(cfg.ruta_db)
    v = VigilanteProhibiciones(cfg, db, RelojFalso())
    reloj = RelojFalso()
    v.tick(reloj.t, "chrome", "YouTube")
    reloj.avanzar(30)
    v.tick(reloj.t, "chrome", "YouTube")
    # solo contó UNA vez el delta (30 s), no doble
    assert v.resumen()["youtube"] == 0.5
    db.cerrar()


def test_tope_de_delta_anti_suspension(cfg):
    """Un hueco enorme entre ciclos (equipo dormido) no cuenta entero."""
    v, db, reloj = _montar(cfg, [{"patron": "youtube", "limite_min_dia": 60}])
    reloj.avanzar(3_600)  # una hora "colgada"
    v.tick(reloj.t, "chrome", "YouTube")
    # solo contó el tope de 90 s, no la hora entera
    assert v.resumen()["youtube"] == 1.5
    db.cerrar()
