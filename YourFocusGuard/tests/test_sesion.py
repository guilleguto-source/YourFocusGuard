"""Modo sesión (guardián de tarea): reglas por predicados sin capturas.

Cubre el guardián puro (R1/R2, auxiliares, excluidas, reanudar) y la
integración con el motor: estado ESCALADA, evidencia única, retoma,
cierre manual/por tiempo, pausas y vuelta al pipeline normal.
"""
from __future__ import annotations

from yourfocusguard.constants import Estado, TipoEvento
from yourfocusguard.session_guard import (
    MOTIVO_FUERA,
    MOTIVO_INACTIVO,
    GuardianSesion,
    Presencia,
)
from test_engine import (
    NotifierFake,
    RelojFalso,
    VentanaGuion,
    escribir_control,
)

T0 = 1_000_000.0


# --------------------------------------------------------------------------- #
# Guardián puro
# --------------------------------------------------------------------------- #

def guardia(cfg, reloj=None):
    return GuardianSesion(cfg.sesion, reloj or (lambda: 0.0))


def test_r1_fuera_de_app_dispara_al_umbral(cfg):
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop"])
    # en app al inicio
    assert g.evaluar(T0 + 5, Presencia.EN_APP, 1.0).senal is None
    # se va: 15 s, 45 s -> aún nada
    assert g.evaluar(T0 + 20, Presencia.FUERA, 1.0).senal is None
    assert g.evaluar(T0 + 50, Presencia.FUERA, 1.0).senal is None
    # 65 s fuera -> R1
    ev = g.evaluar(T0 + 65, Presencia.FUERA, 1.0)
    assert ev.senal == MOTIVO_FUERA
    assert ev.sostenido_seg >= 60


def test_r1_se_rearma_al_volver(cfg):
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop"])
    g.evaluar(T0 + 5, Presencia.EN_APP, 1.0)
    g.evaluar(T0 + 70, Presencia.FUERA, 1.0)          # 65 s fuera -> dispararía
    g.evaluar(T0 + 75, Presencia.EN_APP, 1.0)          # volvió: resetea
    ev = g.evaluar(T0 + 90, Presencia.FUERA, 1.0)      # 15 s fuera -> nada
    assert ev.senal is None


def test_r2_inactivo_en_app_dispara(cfg):
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop"])
    g.evaluar(T0 + 5, Presencia.EN_APP, 2.0)
    ev = g.evaluar(T0 + 70, Presencia.EN_APP, 70.0)
    assert ev.senal == MOTIVO_INACTIVO
    assert ev.sostenido_seg >= 60


def test_seg_en_app_no_acumula_en_inactividad(cfg):
    cfg.sesion.segundos_inactivo = 60.0
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop"])
    g.evaluar(T0, Presencia.EN_APP, 0.0)
    g.evaluar(T0 + 10, Presencia.EN_APP, 5.0)  # 10s activo -> suma 10s
    assert g.seg_en_app == 10.0

    # Usuario inactivo (idle >= 60s) durante los siguientes 300s
    g.evaluar(T0 + 310, Presencia.EN_APP, 300.0)
    # seg_en_app NO debe haber sumado esos 300s
    assert g.seg_en_app == 10.0



def test_visible_en_otro_monitor_cuenta_como_presente(cfg):
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop"])
    g.evaluar(T0 + 5, Presencia.EN_APP, 1.0)
    # Chrome al frente pero Lightroom sigue visible en el otro monitor
    for t in (T0 + 30, T0 + 90, T0 + 200):
        assert g.evaluar(t, Presencia.VISIBLE, 1.0).senal is None


def test_auxiliar_y_excluida_reinician_la_ausencia(cfg):
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop"], apps_aux=["explorer"])
    g.evaluar(T0 + 5, Presencia.EN_APP, 1.0)
    g.evaluar(T0 + 40, Presencia.AUXILIAR, 1.0)   # moviendo RAWs en explorer
    g.evaluar(T0 + 44, Presencia.EXCLUIDA, 1.0)   # consultó el banco
    ev = g.evaluar(T0 + 75, Presencia.FUERA, 1.0)  # solo 35 s fuera
    assert ev.senal is None


def test_reanudar_tras_pausa_no_dispara(cfg):
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop"])
    g.evaluar(T0 + 5, Presencia.EN_APP, 1.0)
    g.reanudar(T0 + 600)  # pausa manual de 10 min en el medio
    ev = g.evaluar(T0 + 605, Presencia.FUERA, 1.0)
    assert ev.senal is None  # la pausa no cuenta como ausencia


def test_sin_apps_solo_regla_de_inactividad(cfg):
    g = guardia(cfg)
    g.iniciar(T0, [])
    # ninguna app declarada: R1 desactivada, ausencia no dispara
    assert g.evaluar(T0 + 300, Presencia.FUERA, 1.0).senal is None
    # pero el idle sí
    assert g.evaluar(T0 + 320, Presencia.FUERA, 70.0).senal == MOTIVO_INACTIVO


def test_matcheo_regex_de_apps(cfg):
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop", "light.?room"], apps_aux=["bridge"])
    assert g.matchea_objetivo("photoshop")
    assert g.matchea_objetivo("lightroomclassic")
    assert not g.matchea_objetivo("chrome")
    assert g.matchea_auxiliar("bridge")
    # patrón inválido -> literal, nunca rompe
    g2 = guardia(cfg)
    g2.iniciar(T0, ["ap(p(s"])
    assert not g2.matchea_objetivo("chrome")


def test_resumen_de_cierre(cfg):
    g = guardia(cfg)
    g.iniciar(T0, ["photoshop"])
    g.evaluar(T0 + 10, Presencia.EN_APP, 1.0)
    g.evaluar(T0 + 20, Presencia.FUERA, 1.0)
    g.evaluar(T0 + 30, Presencia.EN_APP, 1.0)
    g.disparos = 2
    r = g.cerrar(T0 + 30)
    assert r["duracion_min"] == 0.5
    assert r["min_en_app"] >= 0.2
    assert r["disparos"] == 2
    assert g.activa is False


# --------------------------------------------------------------------------- #
# Integración con el motor
# --------------------------------------------------------------------------- #

class IdleScript:
    def __init__(self, valor=2.0):
        self.valor = valor

    def __call__(self):
        return self.valor


def montar_sesion(cfg, reloj, ventana, visibles=None, idle=None, camara=None):
    """Agente con proveedores falsos + sesión iniciada por archivo de control."""
    from yourfocusguard.brain.router import BrainRouter
    from yourfocusguard.engine import Agent
    from yourfocusguard.storage.db import EventDB

    # v0.4.0: la captura de evidencia dejó de ser el default; estos tests
    # la ejercitan explícitamente.
    cfg.sesion.capturar_al_disparar = True

    db = EventDB(cfg.ruta_db)
    router = BrainRouter(cfg)
    notifier = NotifierFake()
    capturas = {"n": 0}

    def grab():
        capturas["n"] += 1
        return b"jpeg-evidencia"

    agente = Agent(
        cfg, db, router, notifier=notifier,
        window_fn=ventana,
        idle_fn=(idle or IdleScript()),
        fullscreen_fn=lambda: False,
        visibles_fn=(lambda patrones: set(visibles) if visibles else set()),
        grab_fn=grab, camara=camara, reloj=reloj, dormir=lambda s: None,
        bloqueo_fn=lambda: False,
        consola=False, hotkey=False,
    )
    agente.sesion_id = db.abrir_sesion("pc_diseno", "")
    return agente, db, notifier, capturas


def iniciar_sesion(agente, reloj, apps=("photoshop",), minutos=0, texto="editar fotos"):
    escribir_control(
        agente.cfg,
        {"cmd": "session_start", "texto": texto, "apps": list(apps),
         "apps_aux": [], "minutos": minutos},
    )
    agente._tick(reloj.t)
    assert agente.guardia.activa
    assert agente.tarea == texto


def test_sesion_activa_cero_capturas_y_cero_nube(cfg):
    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "boda.CR3 - Lightroom")])
    )
    iniciar_sesion(agente, reloj)
    for _ in range(6):  # ~30 s trabajando tranquilo
        reloj.avanzar(5)
        agente._tick(reloj.t)
    assert capturas["n"] == 0          # sin capturas: la propuesta del usuario
    assert agente.estado == Estado.FOCO


def test_fuera_de_app_60s_dispara_escalada(cfg):
    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("chrome", "YouTube - gatitos")])
    )
    iniciar_sesion(agente, reloj)
    reloj.avanzar(15)
    agente._tick(reloj.t)              # 15 s fuera: aún nada
    assert agente.off_since is None
    reloj.avanzar(46)
    agente._tick(reloj.t)              # 61 s fuera: R1
    assert agente.guardia.disparos == 1
    assert agente.estado == Estado.ESCALADA
    # backdating honesto: el episodio empezó cuando el usuario se fue
    assert abs(agente.off_since - (reloj.t - 61)) < 1.0
    assert capturas["n"] == 1          # UNA evidencia, no un chorro
    # la escalera sigue viva y sube con el tiempo
    reloj.avanzar(35)
    agente._tick(reloj.t)
    assert notifier.avisos  # N1 disparó
    filas = db.eventos_recientes(30)
    assert any(f["tipo"] == TipoEvento.DESVIO.value for f in filas)


def test_visible_en_otro_monitor_no_dispara(cfg):
    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("chrome", "referencia de colores")]),
        visibles={"photoshop"},
    )
    iniciar_sesion(agente, reloj)
    for _ in range(20):  # ~100 s con Lightroom visible en el otro monitor
        reloj.avanzar(5)
        agente._tick(reloj.t)
    assert agente.off_since is None
    assert capturas["n"] == 0


def test_inactivo_en_app_dispara(cfg):
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "retouching")]), idle=idle
    )
    iniciar_sesion(agente, reloj)
    reloj.avanzar(10)
    agente._tick(reloj.t)
    idle.valor = 75.0                  # se congeló mirando la foto
    reloj.avanzar(5)
    agente._tick(reloj.t)              # R2: episodio abierto (t0 = inicio de sesión)
    assert agente.guardia.disparos == 1
    assert agente.off_since == agente.guardia.inicio
    reloj.avanzar(20)                  # el desvío ya es sostenido (>30 s)
    agente._tick(reloj.t)
    assert agente.estado == Estado.ESCALADA
    filas = db.eventos_recientes(10)
    motivos = [f["motivo"] for f in filas]
    assert any("inactivo_en_app" in (m or "") for m in motivos)


def test_ventana_excluida_no_dispara_ni_captura(cfg):
    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("chrome", "Banco Galicia - Home Banking")])
    )
    iniciar_sesion(agente, reloj)
    for _ in range(30):  # 150 s mirando el banco: ni alerta ni evidencia
        reloj.avanzar(5)
        agente._tick(reloj.t)
    assert agente.guardia.disparos == 0
    assert capturas["n"] == 0


def test_retoma_cierra_episodio_y_puede_rearmar(cfg):
    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("chrome", "YouTube")])
    )
    iniciar_sesion(agente, reloj)
    reloj.avanzar(61)
    agente._tick(reloj.t)              # R1
    assert agente.off_since is not None
    # vuelve a la app: 2 sondeos limpios cierran el episodio
    agente.window_fn = VentanaGuion([("photoshop", "de vuelta")])
    agente.idle_fn = IdleScript(1.0)
    reloj.avanzar(5)
    agente._tick(reloj.t)
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert agente.off_since is None
    filas = db.eventos_recientes(20)
    assert any(f["tipo"] == TipoEvento.RETOMA.value for f in filas)
    # se va de nuevo: segundo episodio permitido (tope 4/hora)
    agente.window_fn = VentanaGuion([("chrome", "otra vez")])
    reloj.avanzar(61)
    agente._tick(reloj.t)
    assert agente.guardia.disparos == 2


def test_fin_por_tiempo_y_vuelta_al_pipeline(cfg):
    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")])
    )
    iniciar_sesion(agente, reloj, minutos=1)
    reloj.avanzar(65)
    agente._tick(reloj.t)              # pasa el fin programado
    assert not agente.guardia.activa
    assert notifier.toasts             # resumen de cierre
    # el pipeline normal vuelve a capturar
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert capturas["n"] >= 1


def test_stop_manual_con_control(cfg):
    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")])
    )
    iniciar_sesion(agente, reloj)
    escribir_control(agente.cfg, {"cmd": "session_stop"})
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert not agente.guardia.activa
    filas = db.eventos_recientes(10)
    assert any("sesion_fin:manual" in (f["motivo"] or "") for f in filas)


def test_pausa_durante_sesion_no_cuenta_como_ausencia(cfg):
    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")])
    )
    iniciar_sesion(agente, reloj)
    escribir_control(agente.cfg, {"cmd": "pause", "minutos": 10})
    reloj.avanzar(5)
    agente._tick(reloj.t)              # entra en pausa
    assert agente.estado == Estado.PAUSA
    reloj.avanzar(600)                 # 10 min de pausa (café)
    escribir_control(agente.cfg, {"cmd": "resume"})
    agente.window_fn = VentanaGuion([("chrome", "noticias")])  # fuera de la app
    agente._tick(reloj.t)              # reanuda: el reloj de ausencia se resetea
    assert agente.off_since is None
    reloj.avanzar(20)
    agente._tick(reloj.t)              # 20 s fuera tras reanudar: nada
    assert agente.off_since is None


def test_estado_json_incluye_bloque_sesion(cfg):
    import json

    reloj = RelojFalso()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")])
    )
    iniciar_sesion(agente, reloj)
    data = json.loads(agente.cfg.ruta_estado.read_text(encoding="utf-8"))
    assert data["sesion"]["activa"] is True
    assert data["sesion"]["apps"] == ["photoshop"]
    assert data["sesion"]["disparos"] == 0
