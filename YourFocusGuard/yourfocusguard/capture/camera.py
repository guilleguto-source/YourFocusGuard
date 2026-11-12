"""Verificación con webcam bajo demanda (v0.2.1, primera pieza de la F3).

Propuesta del usuario, traducida a reglas: la cámara NO se queda encendida
ni toma fotos indiscriminadas. Solo se abre cuando el motor lo pide —
20 s sin tocar nada durante una sesión, o cuando una regla R1/R2 dispara y
hay que tomar medidas— captura UN frame, lo comprime a JPEG y la cierra.
La lámpara de la webcam se enciende 1-2 s por foto, y cada foto queda
registrada en la base con su motivo.

Privacidad (cap. 7 del blueprint):
*   opt-in: ``[camara] habilitada = false`` por defecto;
*   el motor nunca pide una foto en ventanas excluidas ni en modo privado;
*   ``ancho_max`` reduce la imagen antes de guardarla (minimización);
*   ``guardar_fotos = false`` deja todo en RAM: la foto se descarta tras
    registrar su tamaño.

Dependencia: ``opencv-python-headless``. Se importa de forma perezosa: si
no está instalada, el módulo degrada devolviendo None y el agente sigue
funcionando sin cámara (misma filosofía que window_info fuera de Windows).

Para los tests se inyecta un ``cv2`` falso y una fábrica de VideoCapture:
nada de este módulo toca hardware real en el sandbox.
"""
from __future__ import annotations

import logging

from yourfocusguard.config import CamaraCfg

log = logging.getLogger(__name__)


class CamaraWeb:
    """Una foto a la vez. Abre, estabiliza, captura, comprime y suelta."""

    def __init__(
        self,
        cfg: CamaraCfg,
        cv2_mod=None,           # inyectable para tests (módulo cv2 falso)
        fabrica=None,           # inyectable para tests: (clase, indice) -> capture
    ) -> None:
        self.cfg = cfg
        self._cv2_mod = cv2_mod
        self._fabrica = fabrica or (lambda cls, indice: cls(indice))

    # ------------------------------------------------------------------ #
    # Import perezoso de OpenCV
    # ------------------------------------------------------------------ #

    def _cv2(self):
        if self._cv2_mod is not None:
            return self._cv2_mod
        try:
            import cv2 as mod
        except ImportError:
            log.warning(
                "opencv-python-headless no instalado: la cámara queda "
                "desactivada (pip install opencv-python-headless)"
            )
            return None
        self._cv2_mod = mod
        return mod

    # ------------------------------------------------------------------ #
    # Diagnóstico
    # ------------------------------------------------------------------ #

    def diagnostico(self) -> tuple[bool, str]:
        """(ok, detalle) para `doctor` y `test-cam`, sin tomar foto."""
        cv2 = self._cv2()
        if cv2 is None:
            return (False, "falta opencv-python-headless (pip install opencv-python-headless)")
        cap = None
        try:
            cap = self._fabrica(cv2.VideoCapture, self.cfg.indice)
            if cap is None or not cap.isOpened():
                return (
                    False,
                    f"índice {self.cfg.indice} no responde (¿otra app lo está usando?)",
                )
            return (True, f"índice {self.cfg.indice} OK")
        except Exception as exc:
            return (False, str(exc)[:70])
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def disponible(self) -> bool:
        return self.diagnostico()[0]

    # ------------------------------------------------------------------ #
    # La foto
    # ------------------------------------------------------------------ #

    def tomar_foto_jpeg(self) -> bytes | None:
        """UNA foto: None si la cámara no está disponible (nunca lanza)."""
        cv2 = self._cv2()
        if cv2 is None:
            return None
        cap = None
        try:
            cap = self._fabrica(cv2.VideoCapture, self.cfg.indice)
            if cap is None or not cap.isOpened():
                log.warning("webcam índice %s no se pudo abrir", self.cfg.indice)
                return None
            # Frames de estabilización: exposición y balance de blancos
            # automáticos se asientan antes del frame que sí se usa.
            for _ in range(max(1, self.cfg.preframes)):
                cap.grab()
            ok, frame = cap.read()
            if not ok or frame is None:
                log.warning("webcam abrió pero no entregó frame")
                return None

            alto, ancho = frame.shape[:2]
            if ancho > self.cfg.ancho_max:
                escala = self.cfg.ancho_max / ancho
                frame = cv2.resize(
                    frame, (self.cfg.ancho_max, max(1, int(alto * escala)))
                )
            ok, buf = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), int(self.cfg.calidad_jpeg)],
            )
            if not ok:
                log.warning("no se pudo comprimir el frame de la webcam")
                return None
            return bytes(buf.tobytes())
        except Exception:
            log.exception("error inesperado tomando la foto de webcam")
            return None
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
