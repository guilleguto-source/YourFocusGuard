"""Modelo de un frame capturado (solo RAM, nunca se persiste)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # evita import circular en tiempo de ejecución
    from yourfocusguard.brain.base import Verdict


@dataclass
class FrameSnapshot:
    """Una captura de contexto con sus metadatos (blueprint, cap. 3)."""

    ts: float                        # marca temporal unix
    app: str | None = None           # proceso en primer plano ("chrome")
    title: str | None = None         # título de la ventana
    idle_seconds: float | None = None
    jpeg: bytes | None = None        # imagen reducida, solo RAM
    fullscreen: bool = False
    verdict: "Verdict | None" = field(default=None, repr=False)

    def hora_local(self) -> str:
        import time

        return time.strftime("%H:%M:%S", time.localtime(self.ts))
