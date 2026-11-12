"""Avatar embebido en el Panel Web de YourFocusGuard (v0.8.0).

Implementa el protocolo Avatar conectándose directamente con el estado en memoria
o la API HTTP del panel web local (http://127.0.0.1:8756).
No requiere tener OpenPets instalado ni ejecutándose.
"""
from __future__ import annotations

import logging
from typing import Any

from yourfocusguard.avatar.base import (
    limpiar_frase,
    reaccion_para_alerta,
    reaccion_para_estado,
)

log = logging.getLogger(__name__)


class AvatarEmbed:
    """Cara del asistente embebida en el panel web de YourFocusGuard."""

    nombre = "embed"

    def __init__(self, cfg=None) -> None:
        self.cfg = cfg
        self.disponible = False
        self.frases = True if cfg is None else bool(getattr(cfg.avatar, "frases", True))
        self._ultima_reaccion: str | None = None

    def iniciar(self) -> bool:
        """Marca el avatar como disponible."""
        self.disponible = True
        # Fijar mascota por defecto configurada
        mascota = getattr(self.cfg.avatar, "mascota", "null-wisp") if self.cfg else "null-wisp"
        try:
            from yourfocusguard.panel import pet_fijar_mascota, pet_fijar_reaccion
            pet_fijar_mascota(mascota)
            pet_fijar_reaccion("idle")
        except Exception as exc:
            log.debug("AvatarEmbed: no se pudo fijar estado inicial directo: %s", exc)
        log.info("Avatar embebido iniciado con mascota: %s", mascota)
        return True

    def parar(self) -> None:
        self.disponible = False
        try:
            from yourfocusguard.panel import pet_fijar_reaccion
            pet_fijar_reaccion("idle")
        except Exception:
            pass

    def fijar_estado(self, estado: str, detalle: str = "") -> None:
        reaccion = reaccion_para_estado(estado)
        if reaccion == self._ultima_reaccion:
            return
        self._ultima_reaccion = reaccion
        try:
            from yourfocusguard.panel import pet_fijar_reaccion
            pet_fijar_reaccion(reaccion)
        except Exception as exc:
            log.debug("AvatarEmbed: error fijando reacción: %s", exc)

    def al_alerta(self, nivel: int, mensaje: str) -> None:
        if not self.frases:
            return
        frase = limpiar_frase(mensaje)
        if not frase:
            return
        reaccion = reaccion_para_alerta(nivel)
        try:
            from yourfocusguard.panel import pet_decir
            pet_decir(frase, reaccion=reaccion, duracion_ms=4500)
        except Exception as exc:
            log.debug("AvatarEmbed: error al alertar: %s", exc)

    def preguntar(self, texto: str, opciones=()) -> None:
        frase = limpiar_frase(texto)
        try:
            from yourfocusguard.panel import pet_decir
            pet_decir(frase, reaccion="thinking", opciones=list(opciones), duracion_ms=0)
        except Exception as exc:
            log.debug("AvatarEmbed: error al preguntar: %s", exc)

    def respuestas(self) -> list[str]:
        try:
            from yourfocusguard.panel import pet_consumir_respuestas
            return pet_consumir_respuestas()
        except Exception:
            return []
