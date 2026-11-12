"""OpenPets Focus Bridge (v0.7.0, Fase 3).

Tests con un envío falsificado y un agente simulado: nunca se necesita
OpenPets real ni una ventana de escritorio.
"""
from __future__ import annotations

from yourfocusguard.avatar.focus_bridge import (
    FocusBridge,
    crear_focus_bridge,
    METODOS_FOCUS,
)
from yourfocusguard.config import ConcentracionCfg, Config
from yourfocusguard.session_guard import GuardianSesion, Presencia


class _AgenteFalso:
    def __init__(self):
        self.estado = type("E", (), {"value": "FOCO"})()
        self.tarea = "editar fotos"
        self.paused_until = None
        self.confirmados = 0

    def confirmar_sigo(self, ahora):
        self.confirmados += 1


def _cfg():
    cfg = Config.__new__(Config)
    cfg.concentracion = ConcentracionCfg()
    cfg.privacidad = type("P", (), {"pausa_rapida_min": 15})()
    return cfg


def _sesion_activa():
    s = GuardianSesion.__new__(GuardianSesion)
    s.activa = True
    s.apps = ["lightroom"]
    s.apps_aux = []
    return s


def _enviar_falso():
    recibidas = []

    def enviar(discovery, method, params):
        recibidas.append((method, params or {}))
        return {"ok": True, "result": {"ok": True}}

    return enviar, recibidas


def test_metodos_focus_estan_definidos():
    assert "focus.start_session" in METODOS_FOCUS
    assert "focus.pause" in METODOS_FOCUS
    assert "focus.resume" in METODOS_FOCUS
    assert "focus.status" in METODOS_FOCUS
    assert "focus.concentracion" in METODOS_FOCUS
    assert "focus.sigo" in METODOS_FOCUS


def test_bridge_sin_openpets_no_esta_disponible():
    enviar, _ = _enviar_falso()
    # Forzar que hello falle
    def fallar(discovery, method, params):
        raise Exception("no hay openpets")

    cfg = _cfg()
    sesion = _sesion_activa()
    bridge = FocusBridge(cfg, sesion, enviar=fallar)
    assert bridge.iniciar() is False
    assert bridge.disponible() is False


def test_bridge_iniciar_con_openpets():
    enviar, recibidas = _enviar_falso()
    cfg = _cfg()
    sesion = _sesion_activa()
    bridge = FocusBridge(cfg, sesion, enviar=enviar)
    assert bridge.iniciar() is True
    assert bridge.disponible() is True
    assert recibidas[0][0] == "hello"


def test_start_session_inicia_la_sesion():
    enviar, recibidas = _enviar_falso()
    cfg = _cfg()
    sesion = _sesion_activa()
    bridge = FocusBridge(cfg, sesion, enviar=enviar)
    bridge.iniciar()

    ahora = 1_000_000.0
    resultado = bridge.manejar(
        "focus.start_session",
        {"texto": "editar fotos", "apps": ["lightroom", "photoshop"], "minutos": 30},
    )
    assert resultado["ok"] is True
    assert resultado["result"]["sesion"] == "activa"
    assert sesion.activa is True
    assert sesion.apps == ["lightroom", "photoshop"]
    # Se envió una burbuja pet.say
    decir = [r for r in recibidas if r[0] == "pet.say"]
    assert len(decir) >= 1


def test_status_devuelve_estado_del_agente():
    enviar, recibidas = _enviar_falso()
    cfg = _cfg()
    sesion = _sesion_activa()
    agente = _AgenteFalso()
    bridge = FocusBridge(
        cfg, sesion, agente_ref=lambda: agente, enviar=enviar,
    )
    bridge.iniciar()

    resultado = bridge.manejar("focus.status", {})
    assert resultado["ok"] is True
    assert resultado["result"]["estado"] == "FOCO"
    assert resultado["result"]["tarea"] == "editar fotos"
    assert resultado["result"]["sesion_activa"] is True


def test_pause_y_resume():
    enviar, _ = _enviar_falso()
    cfg = _cfg()
    sesion = _sesion_activa()
    agente = _AgenteFalso()
    bridge = FocusBridge(
        cfg, sesion, agente_ref=lambda: agente, enviar=enviar,
    )
    bridge.iniciar()

    r1 = bridge.manejar("focus.pause", {"minutos": 10})
    assert r1["ok"] is True
    assert agente.paused_until is not None

    r2 = bridge.manejar("focus.resume", {})
    assert r2["ok"] is True
    assert agente.paused_until is None


def test_sigo_llama_confirmar_sigo():
    enviar, _ = _enviar_falso()
    cfg = _cfg()
    sesion = _sesion_activa()
    agente = _AgenteFalso()
    bridge = FocusBridge(
        cfg, sesion, agente_ref=lambda: agente, enviar=enviar,
    )
    bridge.iniciar()

    r = bridge.manejar("focus.sigo", {})
    assert r["ok"] is True
    assert agente.confirmados == 1


def test_concentracion_activar_desactivar():
    enviar, _ = _enviar_falso()
    cfg = _cfg()
    cfg.concentracion.habilitado = True
    sesion = _sesion_activa()
    bridge = FocusBridge(cfg, sesion, enviar=enviar)
    bridge.iniciar()

    r1 = bridge.manejar("focus.concentracion", {"activar": True})
    assert r1["ok"] is True
    assert bridge._concentracion is not None
    assert bridge._concentracion.activo is True

    r2 = bridge.manejar("focus.concentracion", {"activar": False})
    assert r2["ok"] is True
    assert bridge._concentracion.activo is False


def test_metodo_desconocido_devuelve_error():
    enviar, _ = _enviar_falso()
    cfg = _cfg()
    sesion = _sesion_activa()
    bridge = FocusBridge(cfg, sesion, enviar=enviar)
    bridge.iniciar()

    r = bridge.manejar("focus.inexistente", {})
    assert r["ok"] is False
    assert "error" in r


def test_crear_focus_bridge_devuelve_instancia():
    cfg = _cfg()
    sesion = _sesion_activa()
    bridge = crear_focus_bridge(cfg, sesion)
    assert isinstance(bridge, FocusBridge)
