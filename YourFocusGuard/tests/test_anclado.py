"""Modo Anclado (v0.4.0) y pregunta contextual.

Reorientación pedida por el usuario: la captura de pantalla sale del mapa,
la cámara es opcional y el agente se guía por el primer plano + la
inactividad. Si sales de la app ancla >1 min te llama; si estás en la app
pero congelado >1 min también.
"""
from __future__ import annotations

import pytest

from tests.test_sesion import (
    IdleScript,
    NotifierFake,
    VentanaGuion,
    escribir_control,
)
from yourfocusguard.constants import Estado
from yourfocusguard.engine import Agent
from yourfocusguard.storage.db import EventDB

T0 = 1_000_000.0


class RelojFalso:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def avanzar(self, seg):
        self.t += seg


class MascotaFake:
    def __init__(self):
        self.alertas = []
        self.estado = None

    def iniciar(self):
        pass

    def parar(self):
        pass

    def fijar_estado(self, estado, tarea=""):
        self.estado = estado

    def al_alerta(self, nivel, texto):
        self.alertas.append((nivel, texto))


class CamaraFake:
    def __init__(self):
        self.fotos = 0

    def tomar_foto_jpeg(self):
        self.fotos += 1
        return b"jpeg-foto"


def montar(cfg, reloj, ventana, idle=None, camara=None, visibles=()):
    db = EventDB(cfg.ruta_db)
    from yourfocusguard.brain.router import BrainRouter

    agente = Agent(
        cfg, db, BrainRouter(cfg), notifier=NotifierFake(),
        window_fn=ventana,
        idle_fn=(idle or IdleScript(2.0)),
        fullscreen_fn=lambda: False,
        visibles_fn=lambda patrones: set(visibles),
        grab_fn=lambda: b"jpeg-no-deberia-llamarse",
        camara=camara, mascota=None, reloj=reloj, dormir=lambda s: None,
        bloqueo_fn=lambda: False,
        consola=False, hotkey=False,
    )
    agente.sesion_id = db.abrir_sesion("pc_diseno", "")
    return agente, db


def cfg_anclado(cfg, apps=("lightroom", "photoshop")):
    """Config de v0.4.0 tal cual la deja load_config: captura apagada."""
    cfg.captura.habilitada = False
    cfg.sesion.apps = list(apps)
    return cfg


# --------------------------------------------------------------------------- #
# Activación automática
# --------------------------------------------------------------------------- #

def test_captura_apagada_activa_modo_anclado_solo(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    agente, db = montar(cfg, reloj, VentanaGuion([("lightroom", "catalogo")]))
    assert not agente.guardia.activa
    agente._tick(reloj.t)
    assert agente.guardia.activa
    assert agente.guardia.apps == ["lightroom", "photoshop"]
    filas = db.eventos_recientes(10)
    assert any("modo_anclado" in (f["motivo"] or "") for f in filas)


def test_modo_anclado_no_captura_ni_usa_nube(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    llamadas = {"grab": 0}

    def grab():
        llamadas["grab"] += 1
        return b"jpeg"

    db = EventDB(cfg.ruta_db)
    from yourfocusguard.brain.router import BrainRouter

    agente = Agent(
        cfg, db, BrainRouter(cfg), notifier=NotifierFake(),
        window_fn=VentanaGuion([("lightroom", "catalogo")]),
        idle_fn=IdleScript(2.0), fullscreen_fn=lambda: False,
        visibles_fn=lambda patrones: set(),
        grab_fn=grab, mascota=None, reloj=reloj, dormir=lambda s: None,
        bloqueo_fn=lambda: False,
        consola=False, hotkey=False,
    )
    agente.sesion_id = db.abrir_sesion("pc_diseno", "")
    for _ in range(5):
        agente._tick(reloj.t)
        reloj.avanzar(5)
    assert llamadas["grab"] == 0  # cero capturas: la petición central de v0.4.0


def test_sin_app_ancla_es_vigilante_de_inactividad(cfg):
    cfg = cfg_anclado(cfg, apps=())
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _ = montar(cfg, reloj, VentanaGuion([("chrome", "nueva pestaña")]), idle=idle)
    agente._tick(reloj.t)
    idle.valor = 61.0
    reloj.avanzar(70)              # el disparo se retrofecha: la escalera escala
    agente._tick(reloj.t)          # R2 sola: congelado > 60 s
    assert agente.guardia.disparos == 1
    assert agente.estado == Estado.ESCALADA


def test_es_pegajoso_tras_un_stop_manual(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    agente, _ = montar(cfg, reloj, VentanaGuion([("lightroom", "catalogo")]))
    agente._tick(reloj.t)
    assert agente.guardia.activa
    escribir_control(agente.cfg, {"cmd": "session_stop"})
    reloj.avanzar(6)
    agente._tick(reloj.t)          # el stop se procesa... y el modo lo re-activa
    assert agente.guardia.activa   # pegajoso: captura apagada = anclado siempre
    assert agente.guardia.disparos == 0  # ...con el guardián recién iniciado


def test_con_captura_habilitada_el_pipeline_clasico_sigue(cfg):
    cfg.captura.habilitada = True
    reloj = RelojFalso()
    agente, _ = montar(cfg, reloj, VentanaGuion([("chrome", "documental")]))
    agente._tick(reloj.t)
    assert not agente.guardia.activa  # monitoreo clásico, como siempre


# --------------------------------------------------------------------------- #
# Pregunta contextual
# --------------------------------------------------------------------------- #

def test_pregunta_verbal_al_congelarse(cfg):
    cfg = cfg_anclado(cfg)
    cfg.alertas.modo = "visual_sonoro"
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    mascota = MascotaFake()
    db = EventDB(cfg.ruta_db)
    from yourfocusguard.brain.router import BrainRouter

    notifier = NotifierFake()
    agente = Agent(
        cfg, db, BrainRouter(cfg), notifier=notifier,
        window_fn=VentanaGuion([("lightroom", "catalogo")]),
        idle_fn=idle, fullscreen_fn=lambda: False,
        visibles_fn=lambda patrones: set(),
        grab_fn=lambda: b"x", camara=None, mascota=mascota,
        reloj=reloj, dormir=lambda s: None, consola=False, hotkey=False,
        bloqueo_fn=lambda: False,
    )
    agente.sesion_id = db.abrir_sesion("pc_diseno", "")
    agente._tick(reloj.t)
    idle.valor = 61.0
    reloj.avanzar(5)
    agente._tick(reloj.t)          # R2 dispara -> pregunta contextual

    assert len(notifier.avisos) == 1
    assert "¿Qué estás haciendo" in notifier.avisos[0]
    assert "¿Necesitas hacer una pausa?" in notifier.avisos[0]
    assert notifier.voces == []    # visual_sonoro no usa la voz
    assert any("¿Qué estás haciendo" in t for _, t in mascota.alertas)
    filas = db.eventos_recientes(10)
    assert any("pregunta_contextual" in (f["accion"] or "") for f in filas)
    assert any("verbal" in (f["motivo"] or "") for f in filas)


def test_pregunta_con_foto_si_hay_camara(cfg):
    cfg = cfg_anclado(cfg)
    cfg.alertas.modo = "completo"
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    cam = CamaraFake()
    agente, db = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]), idle=idle, camara=cam,
    )
    agente._tick(reloj.t)
    idle.valor = 61.0
    reloj.avanzar(5)
    agente._tick(reloj.t)
    # R0 (verificación suave, 20 s) + R2 (disparo) caen en el mismo tick
    assert cam.fotos == 2
    filas = db.eventos_recientes(10)
    preguntas = [f for f in filas if "pregunta_contextual" in (f["accion"] or "")]
    assert preguntas and "foto" in preguntas[-1]["motivo"]


def test_pregunta_al_salir_de_la_app_ancla_menciona_las_anclas(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    agente, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "c")]), visibles=(),
        idle=IdleScript(2.0),
    )
    agente._tick(reloj.t)
    # salir de la app ancla: chrome al frente, nada visible, 61 s
    agente.window_fn = VentanaGuion([("chrome", "noticias")])
    agente._last_app, agente._last_title = "chrome", "noticias"
    reloj.avanzar(61)
    agente._tick(reloj.t)          # R1 dispara
    notifier = agente.notifier
    assert notifier.avisos and "lightroom" in notifier.avisos[0]


# --------------------------------------------------------------------------- #
# Excepciones en prohibiciones (música de YouTube sí, vídeos no)
# --------------------------------------------------------------------------- #

def _cfg_prohibicion(cfg):
    from yourfocusguard.config import ProhibicionCfg

    cfg.prohibiciones.lista = [
        ProhibicionCfg(
            patron="youtube",
            limite_min_dia=60,
            bloqueo_activo=True,
            excepciones=["youtube music", "mix", "lofi"],
        )
    ]
    return cfg


def test_excepcion_no_cuenta_youtube_music(cfg):
    _cfg_prohibicion(cfg)
    from yourfocusguard.vigilante import VigilanteProhibiciones

    reloj = RelojFalso()
    vig = VigilanteProhibiciones(cfg, None, reloj)
    # título de una canción en YouTube Music: NO cuenta
    vig.tick(reloj.t, "chrome", "DJ Lo Fi - estudio — YouTube Music")
    reloj.avanzar(60)
    assert vig.tick(reloj.t, "chrome", "lofi beats mix — youtube music") == []
    assert vig.resumen()["youtube"] == 0
    assert vig.debe_bloquear("chrome", "mix relajante — youtube music") is None


def test_video_de_youtube_si_cuenta_y_bloquea(cfg):
    _cfg_prohibicion(cfg)
    from yourfocusguard.vigilante import VigilanteProhibiciones

    reloj = RelojFalso()
    vig = VigilanteProhibiciones(cfg, None, reloj)
    vig.tick(reloj.t, "chrome", "video gracioso - youtube")
    reloj.avanzar(59)
    for i in range(61):            # 61 minutos de vídeos
        reloj.avanzar(60)
        vig.tick(reloj.t, "chrome", "video gracioso - youtube")
    resumen = vig.resumen()["youtube"]
    assert resumen >= 60
    assert vig.debe_bloquear("chrome", "otro video - youtube") is not None


# --------------------------------------------------------------------------- #
# Panel: excepciones en el overlay
# --------------------------------------------------------------------------- #

def test_panel_overlay_con_excepciones(cfg):
    from yourfocusguard.panel import construir_overlay

    overlay = construir_overlay(
        {
            "prohibiciones": {
                "lista": [
                    {
                        "patron": "youtube",
                        "limite_min_dia": 60,
                        "bloqueo_activo": True,
                        "excepciones": ["YouTube Music", "MIX ", ""],
                    }
                ]
            }
        }
    )
    entrada = overlay["prohibiciones"]["lista"][0]
    assert entrada["excepciones"] == ["youtube music", "mix"]

    # y sobrevive al ciclo de carga + validación
    from yourfocusguard.config import load_config
    from yourfocusguard.panel import escribir_user_toml

    escribir_user_toml(cfg._config_dir / "user.toml", overlay)
    fresca = load_config(perfil="pc", config_dir=cfg._config_dir,
                         datos_carpeta=str(cfg.datos.carpeta))
    assert fresca.prohibiciones.lista[0].excepciones == ["youtube music", "mix"]


def test_payload_estado_expone_captura_y_excepciones(cfg):
    from yourfocusguard.config import load_config
    from yourfocusguard.panel import (
        construir_overlay,
        escribir_user_toml,
        payload_estado,
    )

    # el panel lee SIEMPRE del disco (config fresca): persistimos primero
    overlay = construir_overlay(
        {
            "captura": {"habilitada": True},
            "prohibiciones": {
                "lista": [
                    {
                        "patron": "youtube",
                        "limite_min_dia": 60,
                        "bloqueo_activo": True,
                        "excepciones": ["youtube music", "mix"],
                    }
                ]
            },
        }
    )
    escribir_user_toml(cfg._config_dir / "user.toml", overlay)
    datos = payload_estado(cfg)
    assert datos["config"]["captura_habilitada"] is True
    assert datos["prohibiciones"][0]["excepciones"] == ["youtube music", "mix"]
