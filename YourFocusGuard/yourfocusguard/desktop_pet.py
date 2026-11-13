"""Lanzador de Mascota Flotante Transparente para el Escritorio de Windows (v0.8.2).

Lanza la mascota nativa (desktop_pet_native.py) en un subproceso desacoplado,
utilizando Tkinter puro y transparencia por color clave (-transparentcolor),
sin dependencias de pywebview ni cajas blancas en Windows.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def lanzar_mascota_escritorio(
    puerto: int = 8756, mascota: str = "null-wisp", tamaño: str = "normal"
) -> subprocess.Popen | None:
    """Lanza la mascota flotante nativa en un proceso independiente de Windows."""
    cmd = [
        sys.executable,
        "-m",
        "yourfocusguard.desktop_pet_native",
        str(mascota),
        str(puerto),
        str(tamaño),
    ]
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
    raiz = str(Path(__file__).resolve().parent.parent)
    try:
        proc = subprocess.Popen(
            cmd,
            creationflags=flags,
            close_fds=True,
            cwd=raiz,
        )
        log.info("Mascota nativa de escritorio lanzada (PID: %s)", proc.pid)
        return proc
    except Exception as exc:
        log.warning("No se pudo iniciar la mascota nativa: %s", exc)
        return None


if __name__ == "__main__":
    arg1 = sys.argv[1] if len(sys.argv) > 1 else ""
    arg2 = sys.argv[2] if len(sys.argv) > 2 else ""
    if arg1.isdigit():
        puerto = int(arg1)
        mascota = arg2 or "null-wisp"
    elif arg2.isdigit():
        mascota = arg1 or "null-wisp"
        puerto = int(arg2)
    else:
        mascota = arg1 or "null-wisp"
        puerto = 8756
    lanzar_mascota_escritorio(puerto, mascota)
