"""Contrato común de los cerebros: veredicto JSON idéntico venga de la nube
o de la heurística local (blueprint, cap. 4: "el orquestador no sabe, ni le
importa, quién emitió el veredicto").
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from yourfocusguard.memory.fifo import FrameBuffer


@dataclass
class Verdict:
    """Salida del prompt v1 (Apéndice B), con el origen añadido."""

    continuidad: bool
    desvio: bool
    motivo: str          # redes | video | celular | conversacion | mirada | otro | ninguno
    app_detectada: str
    confianza: float     # 0.0 - 1.0
    accion_sugerida: str  # nada | mascota | aviso | toast | voz
    origen: str          # nube:gemini | nube:openai | heuristica | cache
    ts: float = 0.0

    @property
    def autoritario(self) -> bool:
        """Un veredicto con confianza >= umbral puede cambiar el estado.

        El umbral (0.6 por defecto) lo aporta la configuración; la propiedad
        es una conveniencia para el motor.
        """
        return self.confianza >= 0.6


class BrainUnavailableError(RuntimeError):
    """El cerebro no puede responder ahora mismo (red, clave, JSON inválido...).

    El router la traduce en degradación al Nivel B, nunca en caída del agente.
    """


class Brain(ABC):
    """Interfaz de un módulo de inferencia."""

    name: str = "base"

    @abstractmethod
    def analyze(self, buffer: FrameBuffer, tarea: str = "") -> Verdict:
        """Evalúa la FIFO y devuelve un veredicto con el contrato del prompt v1."""
        raise NotImplementedError
