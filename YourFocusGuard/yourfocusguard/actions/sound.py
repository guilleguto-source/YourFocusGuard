"""Sonido corto suave para el aviso sutil N1 (tabla 5 del blueprint).

En Windows usa ``winsound`` de la librería estándar; en otros sistemas
emite el bell de consola. Nada de sonidos duros: la escalera es gradual
y no punitiva.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def beep_suave() -> bool:
    try:
        if sys.platform == "win32":
            import winsound

            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return True
        print("\a", end="", flush=True)
        return True
    except Exception as exc:  # pragma: no cover
        log.warning("beep falló: %s", exc)
        return False
