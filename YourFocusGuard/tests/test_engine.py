"""Pruebas de integración del motor: máquina de estados, escalera, pausas,
Pomodoro, control por archivo y reglas anti-falso-positivo del cap. 5."""
from __future__ import annotations

import json

from yourfocusguard.brain.base import BrainUnavailableError, Verdict
from yourfocusguard.brain.router import BrainRouter
from yourfocusguard.engine import Agent
from yourfocusguard.memory.fifo import FrameBuffer
from yourfocusguard.memory.models import FrameSnapshot
from yourfocusguard.storage.db import EventDB

T0 = 1_000_000.0


class RelojFalso:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def avanzar(self, seg):
        self.t += seg


class VentanaGuion:
    """Devuelve (app, titulo) de un guion; el último paso se repite."""

    def __init__(self, pasos):
        self.pasos = pasos
        self.i = 0

    def __call__(self):
        paso = self.pasos[min(self.i, len(self.pasos) - 1)]
        self.i += 1
        return paso


class NotifierFake:
    def __init__(self):
        self.avisos, self.toasts, self.voces, self.infos = [], [], [], []

    def aviso(self, m):
        self.avisos.append(m)

    def toast(self, t, m):
        self.toasts.append((t, m))

    def voz(self, t):
        self.voces.append(t)

    def info(self, m):
        self.infos.append(m)


class CerebroFalso:
    name = "falso"

    def __init__(self, veredicto):
        self.veredicto = veredicto

    def analyze(self, buffer, tarea=""):
        return self.veredicto


def _verdict(desvio=False, conf=0.9, origen="heuristica"):
    return Verdict(
        continuidad=not desvio, desvio=desvio, motivo="video" if desvio else "ninguno",
        app_detectada="chrome", confianza=conf, accion_sugerida="nada",
        origen=origen, ts=0.0,
    )


def montar(cfg, reloj, ventana, idle=3.0, cloud=None, fullscreen=False):
    db = EventDB(cfg.ruta_db)
    router = BrainRouter(cfg, cloud=cloud)
    notifier = NotifierFake()
    capturas = {"n": 0}

    def grab():
        capturas["n"] += 1
        return b"jpeg"

    agente = Agent(
        cfg, db, router, notifier=notifier,
        window_fn=ventana, idle_fn=lambda: idle,
        fullscreen_fn=(fullscreen if callable(fullscreen) else (lambda: fullscreen)),
        grab_fn=grab, reloj=reloj, dormir=lambda s: None,
        consola=False, hotkey=False,
    )
    agente.sesion_id = db.abrir_sesion("pc_diseno", "")
    return agente, db, notifier, capturas


def escribir_control(cfg, datos):
    ruta = cfg.ruta_control
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Flujo central: FOCO -> señal -> ESCALADA -> escalera -> retoma
# --------------------------------------------------------------------------- #

def test_ciclo_completo_de_distraccion(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([
        ("pycharm", "tesis cap 3"),        # tick 1: foco
        ("chrome", "YouTube - gatitos"),   # tick 2: primera señal (débil)
        ("chrome", "YouTube - perros"),    # tick 3: autoritaria -> abre episodio
        ("chrome", "YouTube - más"),       # ticks siguientes: sostenido
        ("chrome", "YouTube - x"), ("chrome", "YouTube - y"),
        ("chrome", "YouTube - z"), ("chrome", "YouTube - w"),
        ("pycharm", "tesis cap 3"),        # limpieza 1
        ("pycharm", "tesis cap 4"),        # limpieza 2 -> retoma
    ])
    agente, db, notifier, _ = montar(cfg, reloj, ventana)

    assert agente._tick(reloj.t)["estado"] == "FOCO"

    reloj.avanzar(15)
    r = agente._tick(reloj.t)          # un frame de YouTube: débil, no abre
    assert r["estado"] == "FOCO"
    assert agente.off_since is None

    reloj.avanzar(15)
    agente._tick(reloj.t)              # segundo frame: 0.85, abre episodio
    # el episodio se abre con la PRIMERA señal autoritaria (2.º frame),
    # no se retrodata a la señal débil: regla de transición breve (cap. 5)
    assert agente.off_since == reloj.t
    assert agente.ladder.activo

    reloj.avanzar(15)
    agente._tick(reloj.t)              # +15 s del episodio: aún FOCO
    assert agente.estado.value == "FOCO"

    reloj.avanzar(20)                  # episodio en +35 s: confirma y dispara N0+N1
    r = agente._tick(reloj.t)
    assert r["estado"] == "ESCALADA"
    assert len(notifier.avisos) == 1   # N1

    reloj.avanzar(25)                  # +60 s del episodio: N2
    agente._tick(reloj.t)
    assert len(notifier.toasts) == 1

    reloj.avanzar(30)                  # +90 s: N3 voz -> cooldown
    agente._tick(reloj.t)
    assert len(notifier.voces) == 1
    assert agente.ladder.en_cooldown(reloj.t)

    reloj.avanzar(15)
    r = agente._tick(reloj.t)
    assert r["estado"] == "COOLDOWN"   # sigue distraído, en silencio

    reloj.avanzar(15)                  # primer ciclo limpio
    r = agente._tick(reloj.t)
    assert r["estado"] == "COOLDOWN"   # un ciclo limpio no basta

    reloj.avanzar(15)                  # segundo ciclo limpio: retoma
    r = agente._tick(reloj.t)
    assert r["estado"] == "FOCO"
    assert agente.off_since is None

    # eventos registrados: desvío, alertas (mascota/aviso/toast/voz), retoma
    filas = db.eventos_recientes(50)
    tipos = [f["tipo"] for f in filas]
    assert "desvio" in tipos and "retoma" in tipos
    acciones = [f["accion"] for f in filas if f["tipo"] == "alerta"]
    assert set(acciones) == {"mascota", "aviso", "toast", "voz"}
    db.cerrar()


def test_veredicto_debil_no_rompe_el_episodio(cfg):
    """Un frame neutro (0.35) en medio del desvío no borra el episodio."""
    reloj = RelojFalso()
    ventana = VentanaGuion([
        ("chrome", "YouTube"), ("chrome", "YouTube"),
        ("explorer", "Este equipo"),   # neutra: débil
        ("chrome", "YouTube"),
    ])
    agente, db, notifier, _ = montar(cfg, reloj, ventana)
    for _ in range(4):
        reloj.avanzar(15)
        agente._tick(reloj.t)
    assert agente.off_since is not None
    assert agente.estado.value == "ESCALADA"
    db.cerrar()


def test_veredicto_de_nube_llega_al_motor(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("chrome", "algo"), ("chrome", "algo")])
    agente, db, _, _ = montar(
        cfg, reloj, ventana, cloud=CerebroFalso(_verdict(desvio=True, conf=0.95, origen="nube:gemini"))
    )
    r = agente._tick(reloj.t)
    assert r["origen"] == "nube:gemini"
    assert agente.off_since is not None  # la nube abrió el episodio
    db.cerrar()


# --------------------------------------------------------------------------- #
# Reglas anti-falso-positivo (cap. 5)
# --------------------------------------------------------------------------- #

def test_regla_pantalla_completa_modulo_silencioso(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("chrome", "YouTube"), ("chrome", "YouTube")])
    agente, db, notifier, _ = montar(cfg, reloj, ventana, fullscreen=True)
    for _ in range(6):
        reloj.avanzar(15)
        agente._tick(reloj.t)
    assert agente.estado.value in ("ESCALADA", "COOLDOWN")
    assert not notifier.avisos and not notifier.toasts and not notifier.voces
    db.cerrar()


def test_exclusion_no_captura_nada(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("keepass", "mi bóveda"), ("keepass", "mi bóveda")])
    agente, db, _, capturas = montar(cfg, reloj, ventana)
    r = agente._tick(reloj.t)
    assert r["estado"] == "PAUSA" and r["pausa"] == "privado"
    assert capturas["n"] == 0  # ni una captura: privacidad por construcción
    filas = db.eventos_recientes(5)
    assert any(f["tipo"] == "pausa" and "privado" in (f["motivo"] or "") for f in filas)
    db.cerrar()


def test_idle_ausencia_suspende_y_reanuda(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, _, capturas = montar(cfg, reloj, ventana, idle=200.0)
    r = agente._tick(reloj.t)
    assert r["pausa"] == "ausencia" and capturas["n"] == 0

    agente.idle_fn = lambda: 5.0  # vuelve la actividad
    r = agente._tick(reloj.t)
    assert r["pausa"] is None and capturas["n"] == 1
    filas = db.eventos_recientes(5)
    assert any(f["motivo"] == "reanudacion:ausencia" for f in filas)
    db.cerrar()


# --------------------------------------------------------------------------- #
# Pausas manuales, control y tarea
# --------------------------------------------------------------------------- #

def test_pausa_manual_por_archivo_de_control(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, _, capturas = montar(cfg, reloj, ventana)
    agente._tick(reloj.t)

    escribir_control(cfg, {"cmd": "pause", "minutos": 5})
    reloj.avanzar(15)
    r = agente._tick(reloj.t)
    assert r["pausa"] == "manual" and capturas["n"] == 1
    assert not cfg.ruta_control.exists()  # el comando se consumió

    reloj.avanzar(15)
    r = agente._tick(reloj.t)
    assert r["pausa"] == "manual"

    reloj.avanzar(301)  # la pausa de 5 min venció
    r = agente._tick(reloj.t)
    assert r["pausa"] is None and capturas["n"] == 2
    filas = db.eventos_recientes(6)
    assert any(f["motivo"] == "reanudacion:manual" for f in filas)
    db.cerrar()


def test_pausa_manual_cierra_el_episodio_abierto(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("chrome", "YouTube"), ("chrome", "YouTube"), ("chrome", "YouTube")])
    agente, db, notifier, _ = montar(cfg, reloj, ventana)
    reloj.avanzar(15)
    agente._tick(reloj.t)
    reloj.avanzar(15)
    agente._tick(reloj.t)  # episodio abierto
    assert agente.off_since is not None

    escribir_control(cfg, {"cmd": "pause", "minutos": 10})
    reloj.avanzar(15)
    agente._tick(reloj.t)
    assert agente.off_since is None and not agente.ladder.activo
    db.cerrar()


def test_comando_stop_detiene(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, _, _ = montar(cfg, reloj, ventana)
    escribir_control(cfg, {"cmd": "stop"})
    r = agente._tick(reloj.t)
    assert r["estado"] == "DETENIDO" and agente._parar
    db.cerrar()


def test_comando_task_declara_tarea(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, _, _ = montar(cfg, reloj, ventana)
    escribir_control(cfg, {"cmd": "task", "texto": "Escribir tesis cap 3"})
    agente._tick(reloj.t)
    assert agente.tarea == "Escribir tesis cap 3"
    filas = db.eventos_recientes(5)
    assert any(f["tipo"] == "tarea" for f in filas)
    assert json.loads(cfg.ruta_estado.read_text(encoding="utf-8"))["tarea"] == "Escribir tesis cap 3"
    db.cerrar()


def test_state_json_se_escribe(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, _, _ = montar(cfg, reloj, ventana)
    agente._tick(reloj.t)
    estado = json.loads(cfg.ruta_estado.read_text(encoding="utf-8"))
    assert estado["estado"] == "FOCO"
    assert estado["maquina"] == "pc_diseno"
    assert estado["cerebro"] == "heuristica"
    db.cerrar()


# --------------------------------------------------------------------------- #
# Pomodoro
# --------------------------------------------------------------------------- #

def test_pomodoro_ciclo_y_pausa(cfg):
    cfg.pomodoro.foco_min = 0.25   # 15 s de foco para la prueba
    cfg.pomodoro.pausa_min = 0.1   # 6 s de pausa
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, notifier, capturas = montar(cfg, reloj, ventana)

    agente._tick(reloj.t)                    # arranca el conteo de foco
    assert agente.pom_fase == "foco"

    reloj.avanzar(15)
    r = agente._tick(reloj.t)                # 15 s >= 0.25 min: pausa Pomodoro
    assert agente.pom_ciclos == 1
    assert agente.pom_fase == "pausa"
    assert r["pausa"] == "pomodoro" or agente.pom_fase == "pausa"
    assert len(notifier.toasts) == 1         # aviso de ciclo completado

    reloj.avanzar(15)                        # la pausa de 6 s ya venció
    r = agente._tick(reloj.t)
    assert agente.pom_fase == "foco"
    assert r["pausa"] is None
    filas = db.eventos_recientes(10)
    assert any(f["motivo"] == "pomodoro:ciclo_1" for f in filas)
    assert any(f["motivo"] == "fin_pausa_pomodoro" for f in filas)
    db.cerrar()


def test_pausa_manual_congela_el_pomodoro(cfg):
    cfg.pomodoro.foco_min = 0.25
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, _, _ = montar(cfg, reloj, ventana)
    agente._tick(reloj.t)

    escribir_control(cfg, {"cmd": "pause", "minutos": 10})
    for _ in range(3):
        reloj.avanzar(15)
        agente._tick(reloj.t)                # 45 s en pausa manual
    assert agente.pom_acumulado == 0.0       # el foco no acumuló
    assert agente.pom_fase == "foco"
    db.cerrar()


# --------------------------------------------------------------------------- #
# Degradación del router registrada por el agente
# --------------------------------------------------------------------------- #

def test_fallo_de_nube_queda_registrado(cfg):
    class NubeRota:
        name = "falso"

        def analyze(self, buffer, tarea=""):
            raise BrainUnavailableError("sin red")

    reloj = RelojFalso()
    ventana = VentanaGuion([("apprararela", "algo")])
    agente, db, _, _ = montar(cfg, reloj, ventana, cloud=NubeRota())
    r = agente._tick(reloj.t)
    assert r["origen"] == "heuristica"       # degradó sin morir
    filas = db.eventos_recientes(5)
    assert any(f["tipo"] == "cerebro" and "fallback" in (f["motivo"] or "") for f in filas)
    db.cerrar()


def test_fifo_no_acumula_mas_de_lo_configurado(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, _, _ = montar(cfg, reloj, ventana)
    for _ in range(8):
        reloj.avanzar(15)
        agente._tick(reloj.t)
    assert len(agente.fifo) == cfg.captura.fifo_frames
    db.cerrar()


def test_refuerzo_positivo_en_foco_continuo(cfg):
    from yourfocusguard.constants import Estado
    cfg.alertas.refuerzo_positivo = True
    cfg.alertas.refuerzo_intervalo_min = 10  # 600 segundos
    cfg.alertas.tts_habilitado = False       # evitar audio en test

    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "trabajo_tesis")])
    agente, db, _, _ = montar(cfg, reloj, ventana)

    # 1. Primer tick entra en FOCO
    agente._tick(reloj.t)
    filas = db.eventos_recientes(10)
    assert not any(f["tipo"] == "refuerzo" for f in filas)

    # 2. Avanzar 9 minutos (540s) en foco continuo: no debe disparar aún
    reloj.avanzar(540)
    agente._tick(reloj.t)
    filas = db.eventos_recientes(10)
    assert not any(f["tipo"] == "refuerzo" for f in filas)

    # 3. Avanzar 65 segundos más (total > 600s): debe disparar refuerzo
    reloj.avanzar(65)
    agente._tick(reloj.t)
    filas = db.eventos_recientes(10)
    refuerzos = [f for f in filas if f["tipo"] == "refuerzo"]
    assert len(refuerzos) == 1
    assert "10_min_foco_continuo" in refuerzos[0]["motivo"]

    # 4. Si se rompe el foco (desvío), la racha se reinicia
    reloj.avanzar(60)
    agente.off_since = reloj.t
    agente.estado = Estado.ESCALADA
    agente._comprobar_refuerzo_positivo(reloj.t)
    assert agente._foco_continuo_desde is None

    db.cerrar()
