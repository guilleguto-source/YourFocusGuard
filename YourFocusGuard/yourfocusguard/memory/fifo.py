"""Cola FIFO de los últimos N frames: la memoria antes que el juicio.

Reglas del blueprint que materializa esta clase:

* ventana de 5 frames a razón de una captura cada 15 s => 45-75 s de contexto
  (cap. 3): suficiente para distinguir un alt-tab de una deriva real;
* vive únicamente en RAM y se sobreescribe: no hay disco ni historial visual;
* un frame aislado nunca condena: el juicio de sostenibilidad es del motor.
"""
from __future__ import annotations

from collections import deque

from yourfocusguard.memory.models import FrameSnapshot


class FrameBuffer:
    """deque con maxlen: empujar el frame 6 expulsa al 1. Cero retención."""

    def __init__(self, frames: int = 5) -> None:
        self._q: deque[FrameSnapshot] = deque(maxlen=frames)

    def push(self, snap: FrameSnapshot) -> None:
        self._q.append(snap)

    def latest(self) -> FrameSnapshot | None:
        return self._q[-1] if self._q else None

    def previous(self) -> FrameSnapshot | None:
        """El frame anterior al último (para la regla de transición breve)."""
        return self._q[-2] if len(self._q) >= 2 else None

    def __len__(self) -> int:
        return len(self._q)

    def __getitem__(self, indice: int) -> FrameSnapshot:
        return self._q[indice]

    def all(self) -> list[FrameSnapshot]:
        return list(self._q)

    # ------------------------------------------------------------------ #
    # Resúmenes para el prompt y la consola
    # ------------------------------------------------------------------ #

    def history_lines(self) -> list[str]:
        """Una línea por frame: hora | app | título truncado | veredicto."""
        lineas = []
        for snap in self._q:
            estado = "-"
            if snap.verdict is not None:
                estado = "desvio" if snap.verdict.desvio else "continuidad"
                estado += f" ({snap.verdict.confianza:.2f})"
            titulo = (snap.title or "")[:60]
            lineas.append(
                f"{snap.hora_local()} | {snap.app or '?'} | {titulo} | {estado}"
            )
        return lineas

    def sample_images(self, n: int = 2) -> list[tuple[float, bytes]]:
        """Hasta ``n`` (ts, jpeg) repartidas por la ventana, la última incluida.

        El prompt pide "una secuencia ordenada de 2 a 5 capturas"; con 2
        imágenes por análisis se mantiene el coste estimado del cap. 4.
        """
        snaps = [s for s in self._q if s.jpeg]
        if not snaps:
            return []
        if len(snaps) <= n:
            elegidos = snaps
        else:
            paso = (len(snaps) - 1) / (n - 1)
            indices = {round(i * paso) for i in range(n)}
            elegidos = [snaps[i] for i in sorted(indices)]
        return [(s.ts, s.jpeg) for s in elegidos]
