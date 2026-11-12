"""Segundos de inactividad de entrada (Windows, vía GetLastInputInfo).

Alimenta dos reglas del blueprint: la heurística del Nivel B (cap. 4) y la
regla 5 anti-falso-positivo: idle > 2 min suspende los ciclos (cap. 5), y en
el Modo Anclado es la regla R2 completa.

v0.5.0: se corrige el contador de ticks. ``GetTickCount`` está en
**kernel32**, no en user32: la llamada anterior fallaba siempre con
"function 'GetTickCount' not found" y ``get_idle_seconds`` devolvía None, con
lo que R2 (y la foto de verificación por inactividad) quedaban mudas en
Windows real. Los tests no lo detectaban porque inyectan un reloj falso.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

_MASCARA_32 = 0xFFFFFFFF


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


def delta_ms_32(ticks: int, ultimo_input: int) -> int:
    """Milisegundos transcurridos con aritmética de 32 bits (sin desbordes).

    ``GetLastInputInfo`` y ``GetTickCount`` son contadores de 32 bits desde el
    arranque; restarlos como enteros sin signo y enmascarar resuelve el salto
    de los 49,7 días sin comparar contra un reloj de 64 bits distinto.
    """
    return ((int(ticks) - int(ultimo_input)) & _MASCARA_32)


def get_idle_seconds() -> float | None:
    """Segundos desde el último input (teclado/ratón); None si no se puede leer."""
    if not _IS_WINDOWS:
        return None
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.GetTickCount.restype = wintypes.DWORD
        ticks = kernel32.GetTickCount()
        return delta_ms_32(ticks, info.dwTime) / 1000.0
    except Exception as exc:  # pragma: no cover
        log.warning("get_idle_seconds falló: %s", exc)
        return None
