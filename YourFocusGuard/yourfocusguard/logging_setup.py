"""Logging del agente: consola + archivo rotante en <datos>/logs/agente.log."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMATO = "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s"
FECHA = "%H:%M:%S"


def setup_logging(nivel: str = "INFO", ruta_log: Path | None = None) -> None:
    """Configura el logger raíz del paquete.

    La consola siempre está (líneas de estado aparte); el archivo rotante
    (5 MB x 3) solo cuando el agente corre de verdad y hay ruta.
    """
    raiz = logging.getLogger("yourfocusguard")
    raiz.setLevel(getattr(logging, nivel.upper(), logging.INFO))
    raiz.handlers.clear()

    consola = logging.StreamHandler()
    consola.setFormatter(logging.Formatter(FORMATO, datefmt=FECHA))
    raiz.addHandler(consola)

    if ruta_log is not None:
        ruta_log.parent.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(
            ruta_log, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        archivo.setFormatter(logging.Formatter(FORMATO))
        raiz.addHandler(archivo)
