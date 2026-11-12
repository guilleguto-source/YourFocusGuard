"""App activa, título de ventana y detección de pantalla completa (Windows).

Se usa ``ctypes`` contra la API de Win32 en lugar de pywin32/pygetwindow:
cero dependencias extra y el mismo resultado (la tabla 9 del blueprint nombra
pygetwindow + pywin32; pywin32 se instala igualmente porque pyttsx3 lo necesita
para la voz SAPI5). En sistemas no Windows degrada devolviendo (None, None)
para que el agente siga arrancando en modo desarrollo.

Extensiones del modo sesión (v0.2.0): enumeración de ventanas visibles en
cualquier monitor (EnumWindows + IsWindowVisible + DWMWA_CLOAKED) para saber
si una app de la sesión sigue "a la vista" aunque no esté en primer plano —
clave con dos monitores (Lightroom en uno, referencia en el otro).
"""
from __future__ import annotations

import ctypes
import logging
import re
import sys
from ctypes import wintypes
from typing import Iterable

log = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_DWMWA_CLOAKED = 14
_MONITORTONEAREST = 2


def _user32():
    return ctypes.windll.user32  # type: ignore[attr-defined]


def _kernel32():
    return ctypes.windll.kernel32  # type: ignore[attr-defined]


def _asegurar_desktop_interactivo() -> None:
    """Enlaza el hilo actual a la estación y escritorio interactivo de Windows (WinSta0\\default)."""
    if not _IS_WINDOWS:
        return
    try:
        user32 = _user32()
        winsta0 = user32.OpenWindowStationW("WinSta0", False, 0x0000037F)
        if winsta0:
            user32.SetProcessWindowStation(winsta0)
        hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception as exc:
        log.debug("No se pudo enlazar a WinSta0: %s", exc)


def _process_name(pid: int) -> str | None:
    """Nombre del ejecutable (sin ruta ni .exe) a partir del PID."""
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
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


def get_active_window() -> tuple[str | None, str | None]:
    """(app, titulo) de la ventana en primer plano; (None, None) si no se puede."""
    if not _IS_WINDOWS:
        return (None, None)
    try:
        user32 = _user32()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            _asegurar_desktop_interactivo()
            hwnd = user32.GetForegroundWindow()
        if not hwnd:
            # Fallback resiliente para conexiones remotas y cambios de foco:
            # el primer elemento de ventanas_visibles() es el tope del Z-order en pantalla.
            vis = ventanas_visibles()
            if vis:
                return (vis[0]["app"], vis[0]["titulo"])
            return (None, None)
        largo = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(hwnd, buf, largo + 1)
        titulo = buf.value or ""

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = _process_name(pid.value) if pid.value else None
        if not app:
            vis = ventanas_visibles()
            if vis:
                return (vis[0]["app"], vis[0]["titulo"])
        return (app, titulo)
    except Exception as exc:  # pragma: no cover - solo errores exóticos de Win32
        log.warning("get_active_window falló: %s", exc)
        return (None, None)


def is_fullscreen() -> bool:
    """True si la ventana en primer plano cubre el monitor principal.

    Se usa para la regla 2 anti-falso-positivo (blueprint, cap. 5): vídeo a
    pantalla completa => modo silencioso automático.
    """
    if not _IS_WINDOWS:
        return False
    try:
        user32 = _user32()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            _asegurar_desktop_interactivo()
            hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        ancho = user32.GetSystemMetrics(0)   # SM_CXSCREEN
        alto = user32.GetSystemMetrics(1)    # SM_CYSCREEN
        cubre = (
            rect.left <= 0
            and rect.top <= 0
            and rect.right >= ancho
            and rect.bottom >= alto
        )
        tiene_barra = bool(user32.GetWindowLongW(hwnd, -16) & 0x00C00000)  # WS_CAPTION
        return cubre and not tiene_barra
    except Exception:  # pragma: no cover
        return False


# --------------------------------------------------------------------------- #
# Ventanas visibles en cualquier monitor (modo sesión)
# --------------------------------------------------------------------------- #

def _indice_monitores() -> dict[int, int]:
    """Mapa handle de monitor -> índice (1..N) según EnumDisplayMonitors."""
    handles: list[int] = []

    def _cb(hmon, hdc, lprect, lparam):
        handles.append(hmon)
        return True

    proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
    )(_cb)
    try:
        _user32().EnumDisplayMonitors(None, None, proc, 0)
    except Exception:  # pragma: no cover
        return {}
    return {h: i + 1 for i, h in enumerate(handles)}


def ventanas_visibles() -> list[dict]:
    """Ventanas "reales" visibles en cualquier monitor.

    Devuelve una lista de dicts {app, titulo, monitor}. Filtra: ocultas,
    minimizadas, cloakeds de UWP, tool-windows y ventanas sin título.
    En no-Windows devuelve [] (modo desarrollo).
    """
    if not _IS_WINDOWS:
        return []
    try:
        _asegurar_desktop_interactivo()
        user32 = _user32()
        monitores = _indice_monitores()
        salida: list[dict] = []

        def _cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            if user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW:
                return True
            try:
                cloak = wintypes.DWORD()
                if (
                    ctypes.windll.dwmapi.DwmGetWindowAttribute(
                        hwnd, _DWMWA_CLOAKED, ctypes.byref(cloak), ctypes.sizeof(cloak)
                    ) == 0
                    and cloak.value != 0
                ):
                    return True  # ventana "fantasma" de UWP: no cuenta
            except Exception:
                pass  # dwmapi ausente: seguimos con los filtros básicos
            largo = user32.GetWindowTextLengthW(hwnd)
            if largo <= 0:
                return True
            buf = ctypes.create_unicode_buffer(largo + 1)
            user32.GetWindowTextW(hwnd, buf, largo + 1)
            titulo = buf.value.strip()
            if not titulo:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            app = _process_name(pid.value) if pid.value else None
            if not app:
                return True
            hmon = user32.MonitorFromWindow(hwnd, _MONITORTONEAREST)
            salida.append(
                {"app": app, "titulo": titulo, "monitor": monitores.get(hmon, 0)}
            )
            return True

        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_cb)
        user32.EnumWindows(proc, 0)
        return salida
    except Exception as exc:  # pragma: no cover
        log.warning("ventanas_visibles falló: %s", exc)
        return []


def apps_visibles(patrones) -> set[str]:
    """Procesos del conjunto dado con alguna ventana visible en algún monitor.

    ``patrones`` son fragmentos de regex sobre el nombre de proceso, igual
    que en [sesion].apps. Coste: una EnumWindows (~ms), sin capturas.
    """
    if not _IS_WINDOWS:
        return set()
    compilados = []
    for p in patrones or ():
        p = (p or "").strip().lower()
        if not p:
            continue
        try:
            compilados.append(re.compile(p))
        except re.error:
            compilados.append(re.compile(re.escape(p)))
    if not compilados:
        return set()
    return {
        v["app"]
        for v in ventanas_visibles()
        if any(c.search(v["app"]) for c in compilados)
    }


# --------------------------------------------------------------------------- #
# Monitores físicos (v0.3.0: selector de pantalla principal del panel)
# --------------------------------------------------------------------------- #

class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def listar_monitores() -> list[dict]:
    """Monitores físicos en orden de escritorio: índice 1..N.

    Devuelve [{indice, ancho, alto, izquierda, arriba, primaria}] con el
    flag de primaria según GetMonitorInfo. Fuera de Windows: [] (el panel
    ofrece entonces un campo numérico manual).
    """
    if not _IS_WINDOWS:
        return []
    try:
        user32 = _user32()
        handles: list[int] = []

        def _cb(hmon, hdc, lprect, lparam):
            handles.append(hmon)
            return True

        proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
            ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
        )(_cb)
        user32.EnumDisplayMonitors(None, None, proc, 0)

        salida: list[dict] = []
        for i, hmon in enumerate(handles, start=1):
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(_MONITORINFO)
            ok = False
            try:
                ok = bool(user32.GetMonitorInfoW(hmon, ctypes.byref(info)))
            except Exception:  # pragma: no cover
                pass
            rect = info.rcMonitor if ok else wintypes.RECT()
            salida.append(
                {
                    "indice": i,
                    "ancho": rect.right - rect.left,
                    "alto": rect.bottom - rect.top,
                    "izquierda": rect.left,
                    "arriba": rect.top,
                    "primaria": bool(info.dwFlags & 1),  # MONITORINFOF_PRIMARY
                }
            )
        return salida
    except Exception as exc:  # pragma: no cover
        log.warning("listar_monitores falló: %s", exc)
        return []


def apps_mas_usadas(
    segundos: float,
    intervalo: float = 1.0,
    neutras: Iterable[str] = (),
    gracia: float = 2.0,
) -> list[tuple[str, int]]:
    """Muestrea el primer plano y devuelve [(app, muestras)] de más a menos.

    v0.5.0: alimenta "detectar apps de la sesión" (panel y CLI). Es un
    muestreo barato de ``get_active_window`` — sin capturas ni permisos.

    ``gracia`` segundos iniciales no cuentan: son los que tardas en cambiar de
    la ventana del panel/consola a tu programa de trabajo.
    """
    import time as _time
    from collections import Counter

    excluidas = {str(n).strip().lower() for n in neutras if str(n).strip()}
    cuenta: Counter[str] = Counter()
    if not _IS_WINDOWS:
        return []
    inicio = _time.monotonic()
    fin = inicio + max(1.0, float(segundos))
    while True:
        ahora = _time.monotonic()
        if ahora - inicio >= max(0.0, float(gracia)):
            app, _titulo = get_active_window()
            if app and app.lower() not in excluidas:
                cuenta[app.lower()] += 1
        if ahora >= fin:
            break
        _time.sleep(max(0.2, float(intervalo)))
    return cuenta.most_common()


# --------------------------------------------------------------------------- #
# Estado de la sesión (v0.5.0): pantalla bloqueada / UAC / secure desktop
# --------------------------------------------------------------------------- #

_DESKTOP_SWITCHDESKTOP = 0x0100



def monitor_ventana_activa() -> int:
    """Índice (1..N) del monitor donde está la ventana al frente; 0 si no se sabe.

    Sirve para ``sesion.monitor_objetivo``: "quiero verme trabajando en el
    monitor 2". Usa el mismo orden de índices que ``listar_monitores``.
    """
    if not _IS_WINDOWS:
        return 0
    try:
        user32 = _user32()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0
        hmon = user32.MonitorFromWindow(hwnd, _MONITORTONEAREST)
        return _indice_monitores().get(hmon, 0)
    except Exception as exc:  # pragma: no cover
        log.debug("monitor_ventana_activa falló: %s", exc)
        return 0



def escritorio_bloqueado() -> bool:
    """True si la sesión está bloqueada (Win+L, salvapantallas, UAC, login).

    Windows conmuta a un "escritorio seguro" cuando bloqueas la sesión; el
    escritorio de entrada deja de ser accesible para tu proceso. Ese es el
    indicador fiable y barato (una llamada cada sondeo), sin tocar el teclado
    ni la pantalla. Fuera de Windows devuelve False.
    """
    if not _IS_WINDOWS:
        return False
    try:
        user32 = _user32()
        escritorio = user32.OpenInputDesktop(0, False, _DESKTOP_SWITCHDESKTOP)
        if not escritorio:
            return True
        try:
            return False
        finally:
            user32.CloseDesktop(escritorio)
    except Exception as exc:  # pragma: no cover - Win32 exótico
        log.debug("escritorio_bloqueado no disponible: %s", exc)
        return False
