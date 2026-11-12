"""Detección de Presencia con MediaPipe (v0.7.0, Fase 3).

Tests con cv2/mediapipe falsificados: nunca se abre una cámara real.
"""
from __future__ import annotations

import types

import pytest

from yourfocusguard.capture.presencia import (
    DeteccionPresencia,
    DetectorPresencia,
    crear_detector_presencia,
)


def _fake_cv2():
    cv2 = types.SimpleNamespace()
    cv2.COLOR_BGR2RGB = 0
    cv2.VideoCapture = lambda idx: None  # no se abre
    return cv2


def _fake_mediapipe():
    mp = types.SimpleNamespace()
    face = types.SimpleNamespace()
    hands = types.SimpleNamespace()

    class _FaceDetection:
        def __init__(self, **kwargs):
            pass

        def process(self, rgb):
            class _Res:
                detections = []
            return _Res()

        def close(self):
            pass

    class _Hands:
        def __init__(self, **kwargs):
            pass

        def process(self, rgb):
            class _Res:
                multi_hand_landmarks = None
            return _Res()

        def close(self):
            pass

    face.FaceDetection = _FaceDetection
    hands.Hands = _Hands
    mp.solutions.face_detection = face
    mp.solutions.hands = hands
    return mp


def test_detector_no_disponible_sin_mediapipe(monkeypatch):
    """Sin mediapipe funcional, disponible() es False y evaluar devuelve error."""
    import yourfocusguard.capture.presencia as mod

    monkeypatch.setattr(mod.DetectorPresencia, "_disponible", lambda self: False)
    cfg = types.SimpleNamespace(
        habilitada=True, indice_camara=0, intervalo_seg=30,
        ausente_para_pausar_seg=120, telefono_en_mano_seg=10,
    )
    det = DetectorPresencia(cfg)
    assert det.disponible() is False


def test_detector_devuelve_error_si_no_habilitada():
    """Con [presencia] habilitada=false, evaluar devuelve 'desactivada'."""
    cfg = types.SimpleNamespace(
        habilitada=False, indice_camara=0, intervalo_seg=30,
        ausente_para_pausar_seg=120, telefono_en_mano_seg=10,
    )
    det = DetectorPresencia(cfg)
    res = det.evaluar()
    assert res.en_silla is False
    assert res.distraccion_posible is False
    assert "desactivada" in (res.error or "")


def test_crear_detector_presencia_devuelve_instancia():
    cfg = types.SimpleNamespace(
        habilitada=False, indice_camara=0, intervalo_seg=30,
        ausente_para_pausar_seg=120, telefono_en_mano_seg=10,
    )
    det = crear_detector_presencia(cfg)
    assert isinstance(det, DetectorPresencia)


def test_detector_cierra_sin_lanzar():
    """cerrar() nunca lanza, incluso si no hay detectores creados."""
    cfg = types.SimpleNamespace(
        habilitada=False, indice_camara=0, intervalo_seg=30,
        ausente_para_pausar_seg=120, telefono_en_mano_seg=10,
    )
    det = DetectorPresencia(cfg)
    det.cerrar()  # no debe lanzar


def test_deteccion_presencia_valores_por_defecto():
    d = DeteccionPresencia()
    assert d.en_silla is False
    assert d.distraccion_posible is False
    assert d.hay_rostro is False
    assert d.telefono_en_mano is False
    assert d.error is None
    assert d.confianza_rostro == 0.0
    assert d.confianza_telefono == 0.0
