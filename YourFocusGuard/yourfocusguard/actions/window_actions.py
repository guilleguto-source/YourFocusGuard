"""Acciones sobre ventanas ajenas: traer al frente y minimizar (Win32 puro).

Nuevas medidas de v0.3.0 pedidas por el usuario:

    - ``traer_al_frente(patron)``: busca la ventana de la app de trabajo
      (Lightroom, Photoshop...) por nombre de proceso o título y la pone en
      primer plano, restaurándola antes si estaba minimizada. Windows no
      deja que un proceso de fondo robe el foco: se usa el truco clásico de
      ``AttachThreadInput`` para que el sistema lo permita.
    - ``minimizar_primera_plano()``: minimiza la ventana activa. Es la medida
      de "bloqueo activo" de las prohibiciones: si el presupuesto de YouTube
      se agotó, cada vez que YouTube vuelve al frente se minimiza.

Fuera de Windows degradan a None/False (los tests inyectan dobles).
"""
from __future__ import annotations

import ctypes
import logging
import re
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

_SW_RESTORE = 9
_SW_MINIMIZE = 6
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080


def _user32():
    return ctypes.windll.user32  # type: ignore[attr-defined]


def _kernel32():
    return ctypes.windll.kernel32  # type: ignore[attr-defined]


def _compilar(patron: str) -> re.Pattern:
    """Fragmento de regex minúsculas; inválido -> literal (nunca rompe)."""
    p = (patron or "").strip().lower()
    try:
        return re.compile(p)
    except re.error:
        return re.compile(re.escape(p))


def matchea(patron: str, app: str | None, titulo: str | None) -> bool:
    """Pure: ¿el patrón matchea el proceso o el título? (testable en cualquier SO)."""
    if not patron or not patron.strip():
        return False
    rx = _compilar(patron)
    if app and rx.search(app.lower()):
        return True
    return bool(titulo and rx.search(titulo.lower()))


def _proceso_de(hwnd: int) -> str | None:
    """Nombre del ejecutable (sin .exe, minúsculas) a partir del hwnd."""
    try:
        user32 = _user32()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        kernel32 = _kernel32()
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED
        if not handle:
            return None
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1].removesuffix(".exe").lower()
            return None
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # pragma: no cover
        return None


def _titulo_de(hwnd: int) -> str:
    try:
        user32 = _user32()
        largo = user32.GetWindowTextLengthW(hwnd)
        if largo <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(hwnd, buf, largo + 1)
        return buf.value or ""
    except Exception:  # pragma: no cover
        return ""


def _candidatas() -> list[tuple[int, str, str]]:
    """Ventanas reales (con título, visibles, no tool-window) con su hwnd."""
    user32 = _user32()
    salida: list[tuple[int, str, str]] = []

    def _cb(hwnd, lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW:
                return True
            titulo = _titulo_de(hwnd)
            if not titulo:
                return True
            app = _proceso_de(hwnd)
            if not app:
                return True
            salida.append((hwnd, app, titulo))
        except Exception:  # pragma: no cover
            pass
        return True

    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_cb)
    user32.EnumWindows(proc, 0)
    return salida


def traer_al_frente(patron: str) -> str | None:
    """Pone al frente la primera ventana que matchee ``patron``.

    Devuelve el título de la ventana movida (para el registro) o None si no
    se encontró / no se pudo. Restaura antes la ventana si estaba minimizada.
    """
    if not patron or not patron.strip():
        return None
    if not _IS_WINDOWS:
        log.debug("traer_al_frente: solo Windows (patrón %r ignorado)", patron)
        return None
    try:
        rx = _compilar(patron)
        elegida: tuple[int, str, str] | None = None
        for hwnd, app, titulo in _candidatas():
            if rx.search(app) or rx.search(titulo.lower()):
                elegida = (hwnd, app, titulo)
                break
        if elegida is None:
            return None
        hwnd = elegida[0]
        user32 = _user32()
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, _SW_RESTORE)
        # Truco estándar para que Windows permita el cambio de foco desde
        # un proceso de fondo: engancharse al hilo que hoy tiene el foco.
        kernel32 = _kernel32()
        fg = user32.GetForegroundWindow()
        hilo_foco = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        hilo_nos = kernel32.GetCurrentThreadId()
        adjuntado = False
        if hilo_foco and hilo_foco != hilo_nos:
            adjuntado = bool(user32.AttachThreadInput(hilo_nos, hilo_foco, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if adjuntado:
                user32.AttachThreadInput(hilo_nos, hilo_foco, False)
        return elegida[2]
    except Exception as exc:  # pragma: no cover
        log.warning("traer_al_frente falló (%s): %s", patron, exc)
        return None


def minimizar_primera_plano() -> bool:
    """Minimiza la ventana activa (medida del bloqueo activo)."""
    if not _IS_WINDOWS:
        log.debug("minimizar_primera_plano: solo Windows")
        return False
    try:
        user32 = _user32()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        return bool(user32.ShowWindow(hwnd, _SW_MINIMIZE))
    except Exception as exc:  # pragma: no cover
        log.warning("minimizar_primera_plano falló: %s", exc)
        return False
