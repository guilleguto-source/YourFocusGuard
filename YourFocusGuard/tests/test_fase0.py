"""Fase 0 (v0.5.0): ausencia real, canal de respuesta y escalera contenida.

Cubre las cuatro correcciones de la revisión:
  * pantalla bloqueada / suspensión / idle largo -> pausa automática, sin avisos
  * la pregunta contextual cubre N0/N1 (no vuelve a sonar a los 20 y 30 s)
  * el "traer al frente" exige llamados con peso y tiempo de desvío
  * respuesta del usuario por avatar, atajo y CLI ("sigo", "pausa", "leyendo")
"""
from __future__ import annotations

from yourfocusguard.brain.router import BrainRouter
from yourfocusguard.constants import Estado
from yourfocusguard.engine import Agent
from yourfocusguard.storage.db import EventDB
from test_engine import NotifierFake, RelojFalso, VentanaGuion
from test_sesion import IdleScript

T0 = 1_000_000.0


class CamaraFake:
    def __init__(self):
        self.fotos = 0

    def tomar_foto_jpeg(self):
        self.fotos += 1
        return b"jpeg-foto"


class MascotaPreguntona:
    """Avatar de prueba que además sabe preguntar (v0.5.0)."""

    def __init__(self):
        self.preguntas: list[tuple[str, tuple]] = []
        self.alertas: list[tuple[int, str]] = []
        self._respuestas: list[str] = []

    def iniciar(self):
        pass

    def parar(self):
        pass

    def fijar_estado(self, estado, detalle=""):
        pass

    def al_alerta(self, nivel, texto):
        self.alertas.append((nivel, texto))

    def preguntar(self, texto, opciones):
        self.preguntas.append((texto, tuple(opciones)))

    def responder(self, clave):
        self._respuestas.append(clave)

    def respuestas(self):
        pendientes = self._respuestas[:]
        self._respuestas.clear()
        return pendientes


def montar(
    cfg,
    reloj,
    ventana,
    idle=None,
    camara=None,
    bloqueo_fn=None,
    visibles=(),
    mascota=None,
    monitor_fn=None,
):
    db = EventDB(cfg.ruta_db)
    notifier = NotifierFake()
    agente = Agent(
        cfg,
        db,
        BrainRouter(cfg),
        notifier=notifier,
        window_fn=ventana,
        idle_fn=(idle or IdleScript(2.0)),
        fullscreen_fn=lambda: False,
        visibles_fn=lambda patrones: set(visibles),
        grab_fn=lambda: b"jpeg",
        camara=camara,
        mascota=mascota,
        bloqueo_fn=(bloqueo_fn or (lambda: False)),
        monitor_fn=(monitor_fn or (lambda: 0)),
        reloj=reloj,
        dormir=lambda s: None,
        consola=False,
        hotkey=False,
    )
    agente.sesion_id = db.abrir_sesion("pc_diseno", "")
    return agente, db, notifier


def cfg_anclado(cfg, apps=("lightroom",)):
    cfg.captura.habilitada = False
    cfg.sesion.apps = list(apps)
    cfg.alertas.modo = "completo"
    return cfg


def abrir_episodio(agente, reloj, idle):
    """Primer tick + R2 por inactividad: deja el episodio abierto."""
    agente._tick(reloj.t)
    idle.valor = 61.0
    reloj.avanzar(5)
    agente._tick(reloj.t)


# --------------------------------------------------------------------------- #
# Ausencia real (pantalla bloqueada / suspensión / idle largo)
# --------------------------------------------------------------------------- #

def test_pantalla_bloqueada_pausa_sin_avisar_ni_fotografiar(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    cam = CamaraFake()
    agente, _, notifier = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]),
        idle=idle, camara=cam, bloqueo_fn=lambda: True,
    )
    for _ in range(6):  # un minuto y medio con la sesión bloqueada
        agente._tick(reloj.t)
        reloj.avanzar(15)

    assert agente._pausa_actual == "ausencia"
    assert agente.estado == Estado.PAUSA
    assert notifier.avisos == [] and notifier.toasts == [] and notifier.voces == []
    assert cam.fotos == 0          # ni selfie con la pantalla bloqueada
    assert agente.off_since is None


def test_idle_largo_pausa_sola_y_reanuda_con_input(cfg):
    cfg = cfg_anclado(cfg)
    cfg.sesion.ausencia_seg = 300
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _, notifier = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]), idle=idle,
    )
    agente._tick(reloj.t)
    idle.valor = 301.0             # 5 min sin tocar nada: te fuiste
    reloj.avanzar(10)
    agente._tick(reloj.t)
    assert agente._pausa_actual == "ausencia"
    assert agente.guardia.disparos == 0
    assert notifier.toasts == []

    idle.valor = 3.0               # volviste y moviste el ratón
    reloj.avanzar(10)
    agente._tick(reloj.t)
    assert agente._pausa_actual is None
    assert agente.guardia.disparos == 0   # ni un aviso por haberte ido


def test_suspension_no_dispara_avalancha_al_volver(cfg):
    cfg = cfg_anclado(cfg)
    cfg.sesion.ausencia_seg = 300
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _, notifier = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]), idle=idle,
    )
    agente._tick(reloj.t)
    reloj.avanzar(600)             # portátil cerrado 10 min
    agente._tick(reloj.t)

    assert agente._pausa_actual == "ausencia"
    assert agente.off_since is None
    assert notifier.toasts == [] and notifier.voces == [] and notifier.avisos == []

    idle.valor = 2.0
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert agente._pausa_actual is None
    assert agente.off_since is None   # sin episodio heredado de la suspensión


# --------------------------------------------------------------------------- #
# Escalera contenida: la pregunta cubre N0/N1
# --------------------------------------------------------------------------- #

def test_la_pregunta_cubre_n0_n1_y_el_siguiente_aviso_es_el_toast(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _, notifier = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]), idle=idle,
    )
    abrir_episodio(agente, reloj, idle)

    assert len(notifier.avisos) == 1          # solo la pregunta contextual
    asunto = notifier.avisos[0]
    assert "¿Qué estás haciendo" in asunto
    toasts_pregunta = len(notifier.toasts)     # el toast de la pregunta

    reloj.avanzar(30)                          # +35 s del episodio
    agente._tick(reloj.t)
    assert len(notifier.avisos) == 1           # N1 no vuelve a sonar
    assert len(notifier.toasts) == toasts_pregunta

    reloj.avanzar(30)                          # +65 s: N2 toast
    agente._tick(reloj.t)
    assert len(notifier.toasts) == toasts_pregunta + 1


def test_traer_al_frente_no_salta_a_los_treinta_segundos(cfg):
    cfg = cfg_anclado(cfg)
    cfg.alertas.traer_al_frente_app = "lightroom"
    cfg.alertas.minutos_antes_de_traer = 2.0
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    llamadas: list[str] = []
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]), idle=idle,
    )
    agente.frente_fn = lambda patron: llamadas.append(patron) or "ventana"
    abrir_episodio(agente, reloj, idle)

    reloj.avanzar(60)             # +65 s: toast y voz, pero no 2 min
    agente._tick(reloj.t)
    assert llamadas == []

    reloj.avanzar(65)             # +130 s: ya son 2 min de desvío
    agente._tick(reloj.t)
    assert llamadas == ["lightroom"]


# --------------------------------------------------------------------------- #
# Canal de respuesta
# --------------------------------------------------------------------------- #

def test_confirmar_sigo_cierra_el_episodio_en_silencio(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, db, notifier = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]), idle=idle,
    )
    abrir_episodio(agente, reloj, idle)
    assert agente.off_since is not None
    voces_pregunta = len(notifier.voces)   # la voz de la pregunta contextual

    agente.confirmar_sigo(reloj.t)
    assert agente.off_since is None
    assert agente.ladder.activo is False
    assert agente.estado == Estado.FOCO
    assert len(notifier.voces) == voces_pregunta   # nada de voz para un "sigo"
    motivos = [
        f["motivo"]
        for f in db.eventos_recientes(10)
        if f["tipo"] == "retoma"
    ]
    assert "confirmado_por_usuario" in motivos


def test_atajo_sigo_se_aplica_en_el_bucle(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]), idle=idle,
    )
    abrir_episodio(agente, reloj, idle)
    agente._pedir_sigo()                   # lo que haría Ctrl+Alt+F11
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert agente.off_since is None


def test_respuesta_pausa_del_avatar_pausa_el_agente(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    mascota = MascotaPreguntona()
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]),
        idle=idle, mascota=mascota,
    )
    abrir_episodio(agente, reloj, idle)
    assert mascota.preguntas                  # el avatar recibió la pregunta
    _, opciones = mascota.preguntas[0]
    assert ("pausa", f"Pausa {cfg.privacidad.pausa_corta_min} min") in opciones

    mascota.responder("pausa")
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert agente.paused_until is not None
    assert agente._pausa_actual == "manual"
    assert agente.off_since is None           # la pausa cierra el aviso


def test_respuesta_leyendo_da_gracia_al_reloj_de_inactividad(cfg):
    cfg = cfg_anclado(cfg)
    cfg.sesion.ausencia_seg = 0                # aquí probamos la gracia, no la ausencia
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    mascota = MascotaPreguntona()
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]),
        idle=idle, mascota=mascota,
    )
    abrir_episodio(agente, reloj, idle)

    mascota.responder("leyendo")
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert agente.off_since is None
    assert agente._gracia_idle_hasta is not None

    idle.valor = 240.0                         # lees sin tocar nada
    reloj.avanzar(60)
    agente._tick(reloj.t)
    assert agente.off_since is None            # todavía no te molesta

    reloj.avanzar(300)                         # la gracia caducó
    agente._tick(reloj.t)
    assert agente.off_since is not None        # ahora sí vuelve R2


# --------------------------------------------------------------------------- #
# Ancla estricta: "quiero Lightroom AL FRENTE"
# --------------------------------------------------------------------------- #

def test_exigir_primer_plano_no_acepta_la_app_en_el_otro_monitor(cfg):
    cfg = cfg_anclado(cfg)
    cfg.sesion.exigir_primer_plano = True
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("chrome", "noticias")]),
        idle=idle, visibles=("lightroom",),
    )
    agente._tick(reloj.t)
    reloj.avanzar(65)
    agente._tick(reloj.t)
    assert agente.guardia.disparos == 1        # visible no basta: debe estar al frente


def test_sin_exigir_primer_plano_visible_cuenta_como_presente(cfg):
    cfg = cfg_anclado(cfg)
    cfg.sesion.exigir_primer_plano = False
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("chrome", "noticias")]),
        idle=idle, visibles=("lightroom",),
    )
    agente._tick(reloj.t)
    reloj.avanzar(65)
    agente._tick(reloj.t)
    assert agente.guardia.disparos == 0        # tolerante: consultar referencias


# --------------------------------------------------------------------------- #
# Regresión Windows: el motivo de la foto trae ":" y rompía el guardado
# --------------------------------------------------------------------------- #

def test_la_foto_se_guarda_aunque_el_motivo_tenga_dos_puntos(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]),
    )
    ruta = agente._guardar_foto(b"jpeg", "disparo:inactivo_en_app")
    assert ruta is not None
    from pathlib import Path

    assert Path(ruta).exists()
    assert ":" not in Path(ruta).name


# --------------------------------------------------------------------------- #
# Fase 1: anclas en caliente, monitor objetivo y detección de apps
# --------------------------------------------------------------------------- #

def test_anclas_cambian_en_caliente_sin_reiniciar(cfg):
    cfg = cfg_anclado(cfg)
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, db, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]), idle=idle,
    )
    agente._tick(reloj.t)
    assert agente.guardia.apps == ["lightroom"]

    cfg.sesion.apps = ["pycharm", "code"]     # el panel/user.toml acaba de cambiar
    reloj.avanzar(5)
    agente._tick(reloj.t)

    assert agente.guardia.apps == ["pycharm", "code"]
    assert any(
        "anclas_actualizadas" in (f["motivo"] or "")
        for f in db.eventos_recientes(10)
    )


def test_una_sesion_declarada_a_mano_no_la_pisa_el_toml(cfg):
    cfg = cfg_anclado(cfg)                    # TOML: lightroom
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("pycharm", "tesis")]), idle=idle,
    )
    agente._iniciar_sesion(
        reloj.t, {"apps": ["pycharm"], "texto": "escribir la tesis"}
    )
    agente._tick(reloj.t)
    assert agente.guardia.apps == ["pycharm"]


def test_monitor_objetivo_exige_el_monitor_del_trabajo(cfg):
    cfg = cfg_anclado(cfg)
    cfg.sesion.monitor_objetivo = 2
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, _, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]),
        idle=idle, monitor_fn=lambda: 1,
    )
    agente._tick(reloj.t)
    reloj.avanzar(65)
    agente._tick(reloj.t)
    assert agente.guardia.disparos == 1       # al frente, pero en el monitor 1

    agente2, _, _ = montar(
        cfg, reloj, VentanaGuion([("lightroom", "catalogo")]),
        idle=idle, monitor_fn=lambda: 2,
    )
    agente2._tick(reloj.t)
    reloj.avanzar(65)
    agente2._tick(reloj.t)
    assert agente2.guardia.disparos == 0


def test_overlay_acepta_apps_aux_y_monitor():
    from yourfocusguard.panel import construir_overlay

    overlay = construir_overlay(
        {
            "sesion": {
                "apps": ["Lightroom", "lightroom", " Photoshop ", ""],
                "apps_auxiliares": ["Explorer", "explorer"],
                "monitor_objetivo": 2,
            }
        }
    )
    assert overlay["sesion"]["apps"] == ["lightroom", "photoshop"]
    assert overlay["sesion"]["apps_auxiliares"] == ["explorer"]
    assert overlay["sesion"]["monitor_objetivo"] == 2


def test_detectar_apps_filtra_neutras(monkeypatch):
    from yourfocusguard.capture import window_info

    secuencia = iter(
        ["lightroom", "lightroom", "explorer", "chrome", "lightroom"]
    )
    monkeypatch.setattr(window_info, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        window_info, "get_active_window", lambda: (next(secuencia, "lightroom"), "x")
    )
    muestras = window_info.apps_mas_usadas(0.25, 0.1, ["explorer"], gracia=0.0)
    assert muestras, "debe muestrear al menos una vez"
    assert muestras[0][0] == "lightroom"
    assert all(app != "explorer" for app, _ in muestras)


def test_detectar_apps_ignora_los_primeros_segundos(monkeypatch):
    """La gracia evita que cuente la ventana del panel/consola."""
    from yourfocusguard.capture import window_info

    monkeypatch.setattr(window_info, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        window_info, "get_active_window", lambda: ("navegador", "panel")
    )
    assert window_info.apps_mas_usadas(1.0, 0.2, [], gracia=5.0) == []


# --------------------------------------------------------------------------- #
# Regresión Windows: GetTickCount está en kernel32, no en user32
# --------------------------------------------------------------------------- #

def test_delta_de_ticks_sobrevive_al_desborde_de_49_dias():
    from yourfocusguard.capture.idle import delta_ms_32

    assert delta_ms_32(5_000, 0) == 5_000
    # el contador de 32 bits vuelve a cero: 26 ms después de 0xFFFFFFF0
    assert delta_ms_32(10, 0xFFFFFFF0) == 26
