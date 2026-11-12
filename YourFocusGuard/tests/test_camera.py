"""Cámara de verificación bajo demanda (v0.2.1, propuesta del usuario).

Cubre el módulo puro (CamaraWeb con cv2 falso: abre, estabiliza, captura,
comprime y libera) y la integración con el motor: R0 de verificación
(20 s congelado -> UNA foto por episodio, silenciosa), foto al disparar
R1/R2, guardado y poda de data/fotos, y los candados de privacidad
(excluidas, cámara desactivada).
"""
from __future__ import annotations

import os
import sys
import time

import pytest

from test_engine import RelojFalso, VentanaGuion, escribir_control
from test_sesion import IdleScript, montar_sesion, iniciar_sesion
from yourfocusguard.capture.camera import CamaraWeb
from yourfocusguard.constants import TipoEvento

T0 = 1_000_000.0


# --------------------------------------------------------------------------- #
# Dobles de OpenCV
# --------------------------------------------------------------------------- #

class FrameFake:
    """Imita un ndarray de OpenCV solo en lo que la cámara usa."""

    def __init__(self, alto=480, ancho=640):
        self.shape = (alto, ancho, 3)


class CapFake:
    def __init__(self, indice, cv2fake, fallar_abrir=False, fallar_leer=False):
        self.indice = indice
        self.grabs = 0
        self.leidas = 0
        self.liberada = False
        self._cv2fake = cv2fake
        self._fallar_abrir = fallar_abrir
        self._fallar_leer = fallar_leer

    def isOpened(self):
        return not self._fallar_abrir

    def grab(self):
        self.grabs += 1
        return True

    def read(self):
        self.leidas += 1
        if self._fallar_leer:
            return (False, None)
        return (True, FrameFake())

    def release(self):
        self.liberada = True


class BufFake:
    """Imita el ndarray que devuelve cv2.imencode (tiene .tobytes)."""

    def __init__(self, datos: bytes):
        self._datos = datos

    def tobytes(self) -> bytes:
        return self._datos


class CV2Fake:
    """Mínimo viable: VideoCapture, resize, imencode y la constante JPEG."""

    IMWRITE_JPEG_QUALITY = 1

    def __init__(self, fallar_abrir=False, fallar_leer=False, ancho_frame=640):
        self.caps: list[CapFake] = []
        self.resizes: list[tuple] = []
        self.calidades: list[int] = []
        self._fallar_abrir = fallar_abrir
        self._fallar_leer = fallar_leer
        self._ancho_frame = ancho_frame

    def VideoCapture(self, indice):
        cap = CapFake(indice, self, self._fallar_abrir, self._fallar_leer)
        self.caps.append(cap)
        return cap

    def resize(self, frame, tamano):
        self.resizes.append(tamano)
        return FrameFake(tamano[1], tamano[0])

    def imencode(self, ext, frame, params):
        assert ext == ".jpg"
        self.calidades.append(dict(zip(params[0::2], params[1::2]))[self.IMWRITE_JPEG_QUALITY])
        return True, BufFake(b"jpeg-de-camara-fake")


def camara(cv2fake, cfg, **kwargs):
    return CamaraWeb(
        cfg.camara,
        cv2_mod=cv2fake,
        fabrica=lambda cls, indice: cv2fake.VideoCapture(indice),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Módulo puro
# --------------------------------------------------------------------------- #

def test_toma_una_foto_estabiliza_comprime_y_libera(cfg):
    fake = CV2Fake()
    jpeg = camara(fake, cfg).tomar_foto_jpeg()
    assert jpeg == b"jpeg-de-camara-fake"
    cap = fake.caps[0]
    assert cap.indice == cfg.camara.indice == 0
    assert cap.grabs == cfg.camara.preframes  # estabilización antes de capturar
    assert cap.leidas == 1
    assert cap.liberada                       # la lámpara se apaga siempre
    assert fake.calidades == [cfg.camara.calidad_jpeg]


def test_reescala_según_ancho_max(cfg):
    cfg.camara.ancho_max = 320
    fake = CV2Fake()
    camara(fake, cfg).tomar_foto_jpeg()
    assert fake.resizes == [(320, 240)]       # 640x480 -> 320x240


def test_sin_reescalado_si_ya_es_pequeña(cfg):
    fake = CV2Fake(ancho_frame=320)
    camara(fake, cfg).tomar_foto_jpeg()
    assert fake.resizes == []                 # 640 == ancho_max: no toca


def test_fallo_al_abrir_devuelve_none_y_no_lanza(cfg):
    fake = CV2Fake(fallar_abrir=True)
    assert camara(fake, cfg).tomar_foto_jpeg() is None


def test_fallo_al_leer_devuelve_none(cfg):
    fake = CV2Fake(fallar_leer=True)
    assert camara(fake, cfg).tomar_foto_jpeg() is None


def test_diagnostico_ok_y_fallo(cfg):
    ok, detalle = camara(CV2Fake(), cfg).diagnostico()
    assert ok and "OK" in detalle
    mal, detalle_mal = camara(CV2Fake(fallar_abrir=True), cfg).diagnostico()
    assert not mal and "índice 0" in detalle_mal


def test_sin_opencv_degrada_sin_romper(cfg, monkeypatch):
    monkeypatch.setitem(sys.modules, "cv2", None)  # import cv2 -> ImportError
    c = CamaraWeb(cfg.camara)
    assert c.tomar_foto_jpeg() is None
    ok, detalle = c.diagnostico()
    assert not ok and "opencv" in detalle


def test_cfg_trae_seccion_camara_con_privacidad_por_defecto(cfg):
    assert cfg.camara.habilitada is False          # opt-in
    assert cfg.camara.indice == 0
    assert cfg.sesion.verificar_con_camara_seg == 20  # la idea del usuario
    assert str(cfg.ruta_fotos).endswith("fotos")


# --------------------------------------------------------------------------- #
# Integración con el motor: R0 de verificación
# --------------------------------------------------------------------------- #

class CamaraFake:
    def __init__(self):
        self.fotos = 0
        self.fallar = False

    def tomar_foto_jpeg(self):
        if self.fallar:
            return None
        self.fotos += 1
        return b"jpeg-camara"


def cfg_con_camara(cfg, **cam):
    cfg.camara.habilitada = True
    for k, v in cam.items():
        setattr(cfg.camara, k, v)
    return cfg


def test_idle_20s_toma_una_foto_y_no_repite_mientras_sigue_congelado(cfg):
    cfg = cfg_con_camara(cfg)
    reloj = RelojFalso()
    cam = CamaraFake()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")]),
        idle=IdleScript(2.0), camara=cam,
    )
    iniciar_sesion(agente, reloj)
    reloj.avanzar(10)
    agente._tick(reloj.t)          # idle 12 s: aún nada
    assert cam.fotos == 0
    idle = agente.idle_fn
    idle.valor = 25.0
    reloj.avanzar(5)
    agente._tick(reloj.t)          # cruza los 20 s: UNA foto
    assert cam.fotos == 1
    for _ in range(6):             # sigue congelado 30 s más: no repite
        reloj.avanzar(5)
        agente._tick(reloj.t)
    assert cam.fotos == 1
    assert agente.off_since is None  # silenciosa: la escalera ni despierta
    assert agente.estado.value != "ESCALADA"


def test_la_verificacion_se_rearma_cuando_vuelve_el_input(cfg):
    cfg = cfg_con_camara(cfg)
    reloj = RelojFalso()
    cam = CamaraFake()
    idle = IdleScript(2.0)
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")]), idle=idle, camara=cam,
    )
    iniciar_sesion(agente, reloj)
    idle.valor = 25.0
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert cam.fotos == 1
    idle.valor = 1.0               # tocó el ratón: rearme
    reloj.avanzar(5)
    agente._tick(reloj.t)
    idle.valor = 30.0              # y volvió a congelarse
    reloj.avanzar(5)
    agente._tick(reloj.t)
    assert cam.fotos == 2


def test_fuera_de_app_no_verifica_pero_al_disparar_si_fotografia(cfg):
    cfg = cfg_con_camara(cfg)
    reloj = RelojFalso()
    cam = CamaraFake()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("chrome", "YouTube")]), idle=IdleScript(2.0),
        camara=cam,
    )
    iniciar_sesion(agente, reloj)
    reloj.avanzar(61)
    agente._tick(reloj.t)          # R1 dispara
    assert agente.guardia.disparos == 1
    assert cam.fotos == 1          # la foto del disparo, no verificaciones previas
    assert capturas["n"] == 1      # y la captura de pantalla de siempre
    filas = db.eventos_recientes(20)
    motivos = [f["motivo"] for f in filas]
    assert any("camara:disparo:fuera_de_app" in (m or "") for m in motivos)
    assert any("evidencia:fuera_de_app" in (m or "") for m in motivos)


def test_r2_verifica_a_los_20_y_mide_a_los_60(cfg):
    """El flujo exacto que pidió el usuario: 20 s foto, 60 s medidas."""
    cfg = cfg_con_camara(cfg)
    reloj = RelojFalso()
    cam = CamaraFake()
    idle = IdleScript(2.0)
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")]), idle=idle, camara=cam,
    )
    iniciar_sesion(agente, reloj)
    idle.valor = 25.0
    reloj.avanzar(5)
    agente._tick(reloj.t)          # foto de verificación
    assert cam.fotos == 1
    assert agente.off_since is None
    idle.valor = 75.0
    reloj.avanzar(5)
    agente._tick(reloj.t)          # R2: medidas
    assert agente.guardia.disparos == 1
    assert cam.fotos == 2          # verificación + disparo
    assert capturas["n"] == 1


def test_camara_desactivada_no_interfiere(cfg):
    reloj = RelojFalso()
    idle = IdleScript(2.0)
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")]), idle=idle,
    )
    assert agente.camara is None
    iniciar_sesion(agente, reloj)
    idle.valor = 70.0
    reloj.avanzar(5)
    agente._tick(reloj.t)          # R2 normal, sin fotos
    assert agente.guardia.disparos == 1
    assert agente.fotos == 0
    assert capturas["n"] == 1


def test_ventana_excluida_nunca_toma_foto(cfg):
    cfg = cfg_con_camara(cfg)
    reloj = RelojFalso()
    cam = CamaraFake()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("chrome", "Banco - Home Banking")]),
        idle=IdleScript(2.0), camara=cam,
    )
    iniciar_sesion(agente, reloj)
    for _ in range(20):
        reloj.avanzar(5)
        agente._tick(reloj.t)
    assert cam.fotos == 0          # ni verificación ni disparo: privacidad
    assert agente.guardia.disparos == 0


def test_fotos_se_guardan_con_motivo_y_se_podan_por_dia(cfg):
    cfg = cfg_con_camara(cfg)
    reloj = RelojFalso()
    cam = CamaraFake()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")]),
        idle=IdleScript(25.0), camara=cam,
    )
    # carpeta de fotos "vieja" que debe desaparecer al arrancar la sesión
    vieja = cfg.ruta_fotos / "2020-01-01"
    vieja.mkdir(parents=True)
    os.utime(vieja, (time.time() - 30 * 86400,) * 2)   # hace 30 días
    iniciar_sesion(agente, reloj)  # _iniciar_sesion poda
    assert not vieja.exists()
    agente._tick(reloj.t)          # idle 25 s -> foto de verificación
    de_hoy = cfg.ruta_fotos / time.strftime("%Y-%m-%d")
    fotos = list(de_hoy.glob("*_verificacion_idle.jpg"))
    assert len(fotos) == 1
    assert fotos[0].read_bytes() == b"jpeg-camara"
    assert agente.fotos == 1


def test_guardar_fotos_false_deja_todo_en_ram(cfg):
    cfg = cfg_con_camara(cfg, guardar_fotos=False)
    reloj = RelojFalso()
    cam = CamaraFake()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")]),
        idle=IdleScript(25.0), camara=cam,
    )
    iniciar_sesion(agente, reloj)
    agente._tick(reloj.t)
    assert cam.fotos == 1          # la foto se tomó...
    assert agente.fotos == 0       # ...pero no se guarda
    assert not cfg.ruta_fotos.exists()
    filas = db.eventos_recientes(10)
    assert any("camara:verificacion_idle" in (f["motivo"] or "") for f in filas)


def test_camara_que_falla_no_rompe_el_guardian(cfg):
    cfg = cfg_con_camara(cfg)
    reloj = RelojFalso()
    cam = CamaraFake()
    cam.fallar = True
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")]),
        idle=IdleScript(25.0), camara=cam,
    )
    iniciar_sesion(agente, reloj)
    agente._tick(reloj.t)          # la cámara devuelve None: registrado y a seguir
    assert cam.fotos == 0
    assert agente.guardia.activa
    filas = db.eventos_recientes(10)
    assert any("camara:verificacion_idle:falla" in (f["motivo"] or "") for f in filas)


def test_estado_json_reporta_fotos_y_camara(cfg):
    import json

    cfg = cfg_con_camara(cfg)
    reloj = RelojFalso()
    cam = CamaraFake()
    agente, db, notifier, capturas = montar_sesion(
        cfg, reloj, VentanaGuion([("photoshop", "editando")]),
        idle=IdleScript(25.0), camara=cam,
    )
    iniciar_sesion(agente, reloj)
    agente._tick(reloj.t)
    data = json.loads(cfg.ruta_estado.read_text(encoding="utf-8"))
    assert data["sesion"]["fotos"] == 1
    assert data["sesion"]["camara"] is True
    assert data["sesion"]["verificado_idle"] is True
