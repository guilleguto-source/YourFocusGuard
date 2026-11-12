"""Buzón de captura rápida de pensamientos (Brain Dump) para Logseq o Markdown.

Permite registrar ideas y tareas al vuelo dictadas por voz sin interrumpir
el flujo de trabajo del usuario. Las notas se anexan al diario de Logseq
(journals/YYYY_MM_DD.md) o a un archivo Markdown local de respaldo.
"""
from __future__ import annotations

import datetime
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yourfocusguard.config import Config

log = logging.getLogger(__name__)

_CANDADO_ESCRITURA = threading.Lock()


def resolver_archivo_destino(cfg: "Config | None" = None) -> Path:
    """Determina la ruta del archivo Markdown donde se anexará la nota.

    Si existe ``carpeta_diario`` (Logseq), genera la ruta del diario diario
    ``YYYY_MM_DD.md``; de lo contrario, anexa a ``archivo_inbox_respaldo``.
    """
    ahora = datetime.datetime.now()
    nombre_diario = ahora.strftime("%Y_%m_%d.md")

    if cfg and getattr(cfg, "notas", None):
        carpeta_str = (cfg.notas.carpeta_diario or "").strip()
        if carpeta_str:
            carpeta = Path(carpeta_str).expanduser()
            if carpeta.is_dir() or carpeta.parent.is_dir():
                carpeta.mkdir(parents=True, exist_ok=True)
                return carpeta / nombre_diario

        # Respaldo configurado
        respaldo_str = cfg.notas.archivo_inbox_respaldo or "./data/inbox_tdah.md"
        ruta_respaldo = Path(respaldo_str).expanduser()
        if not ruta_respaldo.is_absolute():
            base = getattr(cfg, "carpeta_datos", Path("./data"))
            ruta_respaldo = (base.parent / ruta_respaldo).resolve()
        ruta_respaldo.parent.mkdir(parents=True, exist_ok=True)
        return ruta_respaldo

    # Fallback sin config
    fallback = Path("./data/inbox_tdah.md").resolve()
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def guardar_nota_rapida(
    texto: str,
    cfg: "Config | None" = None,
    como_tarea: bool = True,
) -> tuple[bool, str, Path]:
    """Anexa una nota o pensamiento fugaz al diario de Logseq o al inbox local.

    Returns:
        (éxito, mensaje_resumen, ruta_archivo)
    """
    limpio = (texto or "").strip()
    if not limpio:
        return False, "Texto de nota vacío", Path()

    # Si el usuario empezó diciendo "anota que..." o "idea:...", limpiar prefijos redundantes
    for prefijo in ("anota que ", "anota ", "apunta que ", "apunta ", "idea: ", "recordar que ", "recordar "):
        if limpio.lower().startswith(prefijo):
            limpio = limpio[len(prefijo):].strip()
            break

    # Capitalizar primera letra
    if limpio:
        limpio = limpio[0].upper() + limpio[1:]

    ahora = datetime.datetime.now()
    hora_str = ahora.strftime("%H:%M")

    # Formato Logseq / Markdown outliner
    marca = "- TODO " if como_tarea else "- "
    linea = f"{marca}{hora_str} {limpio}\n"

    ruta_destino = resolver_archivo_destino(cfg)

    with _CANDADO_ESCRITURA:
        try:
            ruta_destino.parent.mkdir(parents=True, exist_ok=True)
            # Si el archivo es nuevo, agregar encabezado inicial
            if not ruta_destino.exists() or ruta_destino.stat().st_size == 0:
                with open(ruta_destino, "w", encoding="utf-8") as f:
                    f.write(f"# Diario TDAH — {ahora.strftime('%Y-%m-%d')}\n\n")

            with open(ruta_destino, "a", encoding="utf-8") as f:
                f.write(linea)

            log.info("Nota rápida guardada en %s: %s", ruta_destino.name, limpio)
            return True, f"Anotado en {ruta_destino.name}", ruta_destino
        except Exception as exc:
            log.warning("No se pudo escribir en %s: %s", ruta_destino, exc)
            return False, f"Error al guardar nota: {exc}", ruta_destino
