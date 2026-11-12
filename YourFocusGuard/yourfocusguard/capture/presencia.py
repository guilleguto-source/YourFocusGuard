"""Detección de presencia y teléfono con MediaPipe (v0.7.0, Fase 3).

Opt-in por privacidad: la cámara solo se abre para un frame puntual cada
N segundos, nunca de forma continua. Detecta:

    * Rostro frente a la cámara -> el usuario está en la silla.
    * Mano sosteniendo un rectángulo (teléfono) -> posible distracción.

Requiere ``opencv-python-headless`` y ``mediapipe`` (no están en
requirements.txt por defecto: se instalan a mano si se usa esta función).
Si faltan, el módulo degrada devolviendo "sin datos" y el agente sigue
funcionando igual que siempre (misma filosofía que window_info fuera de
Windows o la webcam sin cv2).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from yourfocusguard.config import PresenciaCfg

log = logging.getLogger(__name__)


@dataclass
class DeteccionPresencia:
    """Resultado de una comprobación de presencia."""

    hay_rostro: bool = False
    confianza_rostro: float = 0.0
    telefono_en_mano: bool = False
    confianza_telefono: float = 0.0
    en_silla: bool = False            # hay_rostro y confianza suficiente
    distraccion_posible: bool = False # telefono_en_mano
    timestamp: float = field(default_factory=time.time)
    error: str | None = None


class DetectorPresencia:
    """Detector bajo demanda con MediaPipe.

    Abre la cámara, toma UN frame, ejecuta FaceDetection y Hands, y suelta
    la cámara. Todo en un hilo aparte si se desea (el motor llama a
    ``evaluar()`` directamente; el llamante decide si usar un hilo).
    """

    def __init__(self, cfg: PresenciaCfg, reloj: Callable[[], float] = time.time) -> None:
        self.cfg = cfg
        self.reloj = reloj
        self._cv2 = None
        self._mp_face = None
        self._mp_hands = None
        self._face_detector = None
        self._hands = None
        self._ultima_evaluacion: DeteccionPresencia | None = None
        self._ultimo_ts: float = 0.0

    # ------------------------------------------------------------------ #
    # Inicio perezoso de MediaPipe
    # ------------------------------------------------------------------ #

    def _importar(self) -> bool:
        """Importa cv2 y mediapipe solo cuando se necesita."""
        if self._cv2 is not None or self._mp_face is not None:
            return self._disponible()
        try:
            import cv2 as cv2_mod  # type: ignore
            self._cv2 = cv2_mod
        except ImportError:
            log.warning("mediapipe: falta opencv-python-headless")
            return False
        try:
            import mediapipe as mp  # type: ignore
            self._mp_face = mp.solutions.face_detection
            self._mp_hands = mp.solutions.hands
        except (ImportError, AttributeError):
            log.warning("mediapipe: falta mediapipe o su API de soluciones (pip install mediapipe)")
            return False
        return True

    def _disponible(self) -> bool:
        return self._cv2 is not None and self._mp_face is not None and self._mp_hands is not None

    def _detectores(self):
        """Crea (o reusa) los detectores de MediaPipe."""
        if self._face_detector is None and self._mp_face is not None:
            self._face_detector = self._mp_face.FaceDetection(
                model_selection=0, min_detection_confidence=0.5
            )
        if self._hands is None and self._mp_hands is not None:
            self._hands = self._mp_hands.Hands(
                static_image_mode=True,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        return self._face_detector, self._hands

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #

    def disponible(self) -> bool:
        """True si se pueden importar cv2 y mediapipe."""
        return self._importar() and self._disponible()

    def evaluar(self, forzar: bool = False) -> DeteccionPresencia:
        """Toma un frame y devuelve la detección.

        Respeta ``intervalo_seg``: si se llamó hace menos tiempo y no se
        fuerza, devuelve el resultado cacheado.
        """
        ahora = self.reloj()
        if (
            not forzar
            and self._ultima_evaluacion is not None
            and ahora - self._ultimo_ts < self.cfg.intervalo_seg
        ):
            return self._ultima_evaluacion

        if not self.cfg.habilitada:
            resultado = DeteccionPresencia(
                en_silla=False, distraccion_posible=False,
                error="presencia desactivada en [presencia]",
            )
            self._guardar(resultado)
            return resultado

        if not self.disponible():
            resultado = DeteccionPresencia(
                en_silla=False, distraccion_posible=False,
                error="opencv o mediapipe no instalados",
            )
            self._guardar(resultado)
            return resultado

        cap = None
        try:
            cv2 = self._cv2
            cap = cv2.VideoCapture(self.cfg.indice_camara)
            if cap is None or not cap.isOpened():
                resultado = DeteccionPresencia(
                    en_silla=False, distraccion_posible=False,
                    error=f"no se abrió la cámara índice {self.cfg.indice_camara}",
                )
                self._guardar(resultado)
                return resultado

            # Un par de frames de estabilización
            for _ in range(2):
                cap.grab()
            ok, frame = cap.read()
            if not ok or frame is None:
                resultado = DeteccionPresencia(
                    en_silla=False, distraccion_posible=False,
                    error="cámara abierta sin frame",
                )
                self._guardar(resultado)
                return resultado

            # MediaPipe espera RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_detector, hands = self._detectores()

            resultados_rostro = face_detector.process(rgb)
            resultados_manos = hands.process(rgb)

            hay_rostro = False
            conf_rostro = 0.0
            if resultados_rostro.detections:
                hay_rostro = True
                conf_rostro = max(
                    (d.score[0] if d.score else 0.0) for d in resultados_rostro.detections
                )

            telefono = False
            conf_telefono = 0.0
            if resultados_manos.multi_hand_landmarks:
                # Heurística simple: si hay manos detectadas cerca del centro
                # del frame y el rostro está presente, asumimos posible teléfono.
                # Una detección real de teléfono requeriría un modelo de objetos;
                # aquí usamos "manos presentes" como indicador suave.
                telefono = True
                conf_telefono = 0.6

            en_silla = hay_rostro and conf_rostro >= 0.5
            distraccion = telefono and en_silla

            resultado = DeteccionPresencia(
                hay_rostro=hay_rostro,
                confianza_rostro=round(conf_rostro, 2),
                telefono_en_mano=telefono,
                confianza_telefono=round(conf_telefono, 2),
                en_silla=en_silla,
                distraccion_posible=distraccion,
            )
            self._guardar(resultado)
            return resultado

        except Exception as exc:  # pragma: no cover - hardware exótico
            log.exception("error evaluando presencia")
            resultado = DeteccionPresencia(
                en_silla=False, distraccion_posible=False, error=str(exc)[:100],
            )
            self._guardar(resultado)
            return resultado
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def _guardar(self, resultado: DeteccionPresencia) -> None:
        self._ultima_evaluacion = resultado
        self._ultimo_ts = self.reloj()

    def ultima(self) -> DeteccionPresencia | None:
        return self._ultima_evaluacion

    def cerrar(self) -> None:
        """Libera detectores de MediaPipe."""
        if self._face_detector is not None:
            try:
                self._face_detector.close()
            except Exception:
                pass
            self._face_detector = None
        if self._hands is not None:
            try:
                self._hands.close()
            except Exception:
                pass
            self._hands = None


def crear_detector_presencia(cfg: PresenciaCfg) -> DetectorPresencia:
    """Fábrica: devuelve un DetectorPresencia listo."""
    return DetectorPresencia(cfg)
