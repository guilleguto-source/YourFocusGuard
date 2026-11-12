"""Pruebas de integración v0.3.0: modos de aviso, traer-al-frente,
prohibiciones con bloqueo, recarga en vivo y cableado de la mascota."""
from __future__ import annotations

import shutil
from pathlib import Path

from yourfocusguard.brain.router import BrainRouter
from yourfocusguard.config import escribir_user_toml, load_config
from yourfocusguard.config import ProhibicionCfg
from yourfocusguard.engine import Agent
from yourfocusguard.storage.db import EventDB

T0 = 3_000_000.0


class RelojFalso:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def avanzar(self, seg):
        self.t += seg


class VentanaGuion:
    def __init__(self, pasos):
        self.pasos = pasos
        self.i = 0

    def __call__(self):
        paso = self.pasos[min(self.i, len(self.pasos) - 1)]
        self.i += 1
        return paso


class NotifierFake:
    def __init__(self):
        self.avisos, self.toasts, self.voces = [], [], []

    def aviso(self, m):
        self.avisos.append(m)

    def toast(self, t, m):
        self.toasts.append((t, m))

    def voz(self, t):
        self.voces.append(t)

    def info(self, m):
        pass


class MascotaFake:
    def __init__(self):
        self.estados, self.alertas, self.paradas = [], [], 0

    def iniciar(self):
        return True

    def fijar_estado(self, estado, detalle=""):
        self.estados.append((estado, detalle))

    def al_alerta(self, nivel, mensaje):
        self.alertas.append((nivel, mensaje))

    def parar(self):
        self.paradas += 1


class FrenteFake:
    """traer_al_fonto inyectable: registra y devuelve un título de ventana."""

    def __init__(self, exito=True):
        self.llamadas = []
        self.exito = exito

    def __call__(self, patron):
        self.llamadas.append(patron)
        return f"ventana de {patron}" if self.exito else None


class MinimizarFake:
    def __init__(self, exito=True):
        self.llamadas = 0
        self.exito = exito

    def __call__(self):
        self.llamadas += 1
        return self.exito


def montar(cfg, reloj, ventana, idle=3.0, frente=None, minimizar=None, mascota=None):
    db = EventDB(cfg.ruta_db)
    router = BrainRouter(cfg)
    notifier = NotifierFake()
    agente = Agent(
        cfg, db, router, notifier=notifier,
        window_fn=ventana, idle_fn=lambda: idle,
        fullscreen_fn=lambda: False,
        grab_fn=lambda: b"jpeg",
        mascota=mascota or MascotaFake(),
        frente_fn=frente or FrenteFake(),
        minimizar_fn=minimizar or MinimizarFake(),
        reloj=reloj, dormir=lambda s: None,
        bloqueo_fn=lambda: False,
        consola=False, hotkey=False,
    )
    agente.sesion_id = db.abrir_sesion("pc_diseno", "")
    return agente, db, notifier


def _sostener(reloj, agente, pasos=8, cada=15):
    """Ticks con la ventana en desvío (guion ya fijado en el último paso)."""
    for _ in range(pasos):
        reloj.avanzar(cada)
        agente._tick(reloj.t)


# --------------------------------------------------------------------------- #
# Modo de aviso: solo visual / completo
# --------------------------------------------------------------------------- #

def test_modo_visual_silencia_sonido(cfg):
    cfg.alertas.modo = "visual"
    reloj = RelojFalso()
    ventana = VentanaGuion([
        ("pycharm", "tesis"),
        ("chrome", "YouTube - a"), ("chrome", "YouTube - b"),
        ("chrome", "YouTube - c"), ("chrome", "YouTube - d"),
        ("chrome", "YouTube - e"), ("chrome", "YouTube - f"),
    ])
    mascota = MascotaFake()
    agente, db, notifier = montar(cfg, reloj, ventana, mascota=mascota)
    _sostener(reloj, agente, pasos=7)

    assert notifier.avisos == []      # N1 (beep) silenciado
    assert notifier.voces == []       # N3 (voz) silenciado
    assert len(notifier.toasts) == 1  # N2 (toast) es visual: sí dispara
    assert mascota.alertas            # la mascota recibe todos los llamados

    acciones = {
        fila["accion"]
        for fila in db._conn.execute(
            "SELECT accion FROM evento WHERE tipo='alerta'"
        ).fetchall()
    }
    assert "mascota" in acciones and "toast" in acciones
    assert "aviso" not in acciones and "voz" not in acciones
    db.cerrar()


def test_modo_completo_trae_al_frente_tras_dos_llamados_y_dos_minutos(cfg):
    """v0.5.0: dos llamados CON PESO (toast/voz) y 2 min de desvío, no 30 s."""
    cfg.alertas.modo = "completo"
    cfg.alertas.traer_al_frente_app = "lightroom"
    cfg.alertas.traer_al_frente_tras = 2
    cfg.alertas.minutos_antes_de_traer = 2.0
    reloj = RelojFalso()
    ventana = VentanaGuion([
        ("pycharm", "tesis"),
        ("chrome", "YouTube - a"), ("chrome", "YouTube - b"),
        ("chrome", "YouTube - c"), ("chrome", "YouTube - d"),
        ("chrome", "YouTube - e"), ("chrome", "YouTube - f"),
        ("chrome", "YouTube - g"), ("chrome", "YouTube - h"),
        ("chrome", "YouTube - i"), ("chrome", "YouTube - j"),
        ("chrome", "YouTube - k"), ("chrome", "YouTube - l"),
    ])
    frente = FrenteFake(exito=True)
    agente, db, _ = montar(cfg, reloj, ventana, frente=frente)

    reloj.avanzar(15)
    agente._tick(reloj.t)  # tick1: pycharm, foco
    reloj.avanzar(15)
    agente._tick(reloj.t)  # tick2: 1.er frame de YouTube (señal débil)
    reloj.avanzar(5)
    agente._tick(reloj.t)  # tick3: 2.º frame -> abre episodio (t0)
    reloj.avanzar(15)
    agente._tick(reloj.t)  # +15 s
    reloj.avanzar(15)
    agente._tick(reloj.t)  # +30 s: N0+N1 (aviso sutil: NO cuentan)
    assert frente.llamadas == []
    reloj.avanzar(15)
    agente._tick(reloj.t)  # +45 s
    reloj.avanzar(15)
    agente._tick(reloj.t)  # +60 s: N2 = 1.er llamado de peso
    reloj.avanzar(15)
    agente._tick(reloj.t)  # +75 s
    reloj.avanzar(15)
    agente._tick(reloj.t)  # +90 s: N3 = 2.º llamado, pero aún no son 2 min
    assert frente.llamadas == []
    reloj.avanzar(15)
    agente._tick(reloj.t)  # +105 s
    assert frente.llamadas == []
    reloj.avanzar(15)
    agente._tick(reloj.t)  # +120 s: 2 min de desvío -> ahora sí
    assert frente.llamadas == ["lightroom"]

    # no repite aunque siga el desvío
    _sostener(reloj, agente, pasos=4)
    assert frente.llamadas == ["lightroom"]

    eventos = [
        fila["motivo"]
        for fila in db._conn.execute(
            "SELECT motivo FROM evento WHERE accion='traer_al_frente'"
        ).fetchall()
    ]
    assert eventos == ["target:lightroom"]
    db.cerrar()


def test_frente_falla_reintenta_en_el_siguiente_llamado(cfg):
    cfg.alertas.modo = "completo"
    cfg.alertas.traer_al_frente_app = "lightroom"
    cfg.alertas.traer_al_frente_tras = 2
    cfg.alertas.minutos_antes_de_traer = 0.0  # este test mira el reintento
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis"), ("chrome", "YouTube - x")])
    frente = FrenteFake(exito=False)  # no hay ventana que traer
    agente, db, _ = montar(cfg, reloj, ventana, frente=frente)
    _sostener(reloj, agente, pasos=32)

    # reintentó en cada llamado posterior, sin marcarse como hecho
    assert frente.llamadas.count("lightroom") >= 2
    eventos = db._conn.execute(
        "SELECT COUNT(*) c FROM evento WHERE accion='traer_al_frente'"
    ).fetchone()["c"]
    assert eventos == 0  # sin éxito no se registra
    db.cerrar()


def test_target_cae_a_la_app_de_la_sesion(cfg):
    """Sin app del panel, el target es la 1.ª app de la sesión activa."""
    cfg.alertas.modo = "completo"
    cfg.alertas.traer_al_frente_app = ""
    cfg.alertas.traer_al_frente_tras = 2
    cfg.alertas.minutos_antes_de_traer = 0.0
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis"), ("chrome", "YouTube - x")])
    frente = FrenteFake()
    agente, db, _ = montar(cfg, reloj, ventana, frente=frente)
    agente._iniciar_sesion(
        reloj.t, {"apps": ["lightroom", "photoshop"], "texto": "editar fotos"}
    )
    # +60 s: N2 (toast) 1.er peso; +90 s: N3 (voz) 2.º peso -> trae al frente
    _sostener(reloj, agente, pasos=12)
    assert frente.llamadas and frente.llamadas[0] == "lightroom"
    db.cerrar()


# --------------------------------------------------------------------------- #
# Prohibiciones: presupuesto, bloqueo activo y exclusiones
# --------------------------------------------------------------------------- #

def test_prohibicion_agota_bloquea_y_trae_la_app(cfg):
    cfg.alertas.traer_al_frente_app = "lightroom"
    cfg.prohibiciones.lista = [
        ProhibicionCfg(patron="youtube", limite_min_dia=5, bloqueo_activo=True)
    ]
    reloj = RelojFalso()
    ventana = VentanaGuion([("chrome", "YouTube - música lofi")])
    frente = FrenteFake()
    minimizar = MinimizarFake()
    agente, db, notifier = montar(cfg, reloj, ventana, frente=frente, minimizar=minimizar)

    # 6 min en YouTube en ticks de 15 s (límite: 5 min)
    for _ in range(24):
        reloj.avanzar(15)
        agente._tick(reloj.t)

    assert minimizar.llamadas >= 1           # bloqueo activo
    assert frente.llamadas.count("lightroom") >= 1  # y vuelve al trabajo
    assert any(
        "presupuesto agotado" in titulo for titulo, _ in notifier.toasts
    ), notifier.toasts
    usados = db.presupuestos_hoy()
    assert usados["youtube"] >= 5 * 60
    db.cerrar()


def test_prohibicion_respetada_en_ventana_excluida(cfg):
    """En una ventana excluida (banca) el agente finge no estar: no cuenta."""
    cfg.prohibiciones.lista = [
        ProhibicionCfg(patron="youtube", limite_min_dia=5, bloqueo_activo=True)
    ]
    reloj = RelojFalso()
    ventana = VentanaGuion([("chrome", "Home Banking - Banco Nación")])
    minimizar = MinimizarFake()
    agente, db, _ = montar(cfg, reloj, ventana, minimizar=minimizar)
    for _ in range(24):
        reloj.avanzar(15)
        agente._tick(reloj.t)
    assert db.presupuestos_hoy() == {}       # titulos_excluidos incluye "banca"
    assert minimizar.llamadas == 0
    db.cerrar()


def test_pausa_suprime_medidas_pero_sigue_contando(cfg):
    cfg.prohibiciones.lista = [
        ProhibicionCfg(patron="youtube", limite_min_dia=5, bloqueo_activo=True)
    ]
    reloj = RelojFalso()
    ventana = VentanaGuion([("chrome", "YouTube - música")])
    frente = FrenteFake()
    minimizar = MinimizarFake()
    agente, db, notifier = montar(cfg, reloj, ventana, frente=frente, minimizar=minimizar)

    # 3 min de los 5: entra en pausa manual de 10 min
    for _ in range(12):
        reloj.avanzar(15)
        agente._tick(reloj.t)
    agente.paused_until = reloj.t + 600
    # 6 min más DENTRO de la pausa: cuenta pero no molesta ni bloquea
    for _ in range(24):
        reloj.avanzar(15)
        agente._tick(reloj.t)
    assert not any("presupuesto" in t for t, _ in notifier.toasts)
    assert minimizar.llamadas == 0
    assert db.presupuestos_hoy()["youtube"] >= 5 * 60

    # vuelve de la pausa y abre YouTube otra vez: ahí sí se bloquea
    agente.paused_until = None
    for _ in range(4):
        reloj.avanzar(15)
        agente._tick(reloj.t)
    assert minimizar.llamadas >= 1
    db.cerrar()


# --------------------------------------------------------------------------- #
# Recarga en vivo del user.toml (panel -> agente)
# --------------------------------------------------------------------------- #

def test_recarga_en_vivo_desde_el_panel(tmp_path):
    origen = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copy(origen / "default.toml", config_dir / "default.toml")
    shutil.copy(origen / "pc.toml", config_dir / "pc.toml")

    cfg = load_config(
        perfil="pc", config_dir=config_dir, datos_carpeta=str(tmp_path / "data")
    )
    cfg.mascota.visible = False
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    agente, db, _ = montar(cfg, reloj, ventana)
    assert cfg.alertas.modo == "completo"

    # el panel guarda cambios (como haría POST /api/config)
    escribir_user_toml(
        config_dir / "user.toml",
        {
            "captura": {"intervalo_seg": 45, "monitor": 2},
            "alertas": {"modo": "visual", "desvio_sostenido_seg": 120},
            "sesion": {"segundos_fuera_app": 120},
        },
    )
    reloj.avanzar(15)
    agente._tick(reloj.t)  # el tick recarga solo

    assert cfg.alertas.modo == "visual"
    assert cfg.captura.intervalo_seg == 45
    assert cfg.captura.monitor == 2
    assert cfg.alertas.desvio_sostenido_seg == 120
    # el guardián de sesión comparte el objeto: ve los cambios
    assert agente.guardia.cfg.segundos_fuera_app == 120
    db.cerrar()


# --------------------------------------------------------------------------- #
# Cableado de la mascota
# --------------------------------------------------------------------------- #

def test_mascota_refleja_estado_y_alertas(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([
        ("pycharm", "tesis"),
        ("chrome", "YouTube - a"), ("chrome", "YouTube - b"),
        ("chrome", "YouTube - c"), ("chrome", "YouTube - d"),
    ])
    mascota = MascotaFake()
    agente, db, _ = montar(cfg, reloj, ventana, mascota=mascota)
    _sostener(reloj, agente, pasos=5)

    assert mascota.estados, "el motor debe alimentar a la mascota en cada tick"
    assert any(e == "ESCALADA" for e, _ in mascota.estados)
    assert mascota.alertas  # los avisos llegan como burbuja
    db.cerrar()


def test_apagar_para_la_mascota(cfg):
    reloj = RelojFalso()
    ventana = VentanaGuion([("pycharm", "tesis")])
    mascota = MascotaFake()
    agente, db, _ = montar(cfg, reloj, ventana, mascota=mascota)
    agente._apagar()
    assert mascota.paradas == 1
    db.cerrar()
