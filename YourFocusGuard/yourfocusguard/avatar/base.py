"""Interfaz del avatar y utilidades puras (v0.6.0).

El motor habla con un ``Avatar`` y no sabe si detrás hay una mascota tkinter,
OpenPets o nada. Todo lo que se puede probar sin sistema operativo vive aquí:
el mapeo de estados a reacciones de OpenPets y la limpieza de frases.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

#: Reacciones válidas del IPC de OpenPets (enum cerrado del cliente oficial).
REACCIONES_OPENPETS = (
    "idle", "thinking", "working", "editing", "running", "testing",
    "waiting", "waving", "success", "error", "celebrating",
)

#: Estado interno del motor -> reacción del avatar.
REACCION_POR_ESTADO = {
    "EN_ESPERA": "idle",
    "FOCO": "working",
    "ESCALADA": "error",
    "COOLDOWN": "thinking",
    "PAUSA": "waiting",
    "DETENIDO": "idle",
}

#: Largo máximo de una burbuja: el host valida mensajes cortos de una línea.
MAX_FRASE = 140


@runtime_checkable
class Avatar(Protocol):
    """Lo mínimo que el motor espera de una cara."""

    disponible: bool

    def iniciar(self) -> bool: ...
    def fijar_estado(self, estado: str, detalle: str = "") -> None: ...
    def al_alerta(self, nivel: int, mensaje: str) -> None: ...
    def preguntar(self, texto: str, opciones=()) -> None: ...
    def respuestas(self) -> list[str]: ...
    def parar(self) -> None: ...


def reaccion_para_estado(estado: str) -> str:
    """FOCO -> working, PAUSA -> waiting…; desconocido -> idle."""
    return REACCION_POR_ESTADO.get(str(estado or "").upper(), "idle")


def reaccion_para_alerta(nivel: int) -> str:
    """Aviso sutil -> pensativo; aviso de peso -> error (cara de '¿eh?')."""
    return "thinking" if int(nivel) <= 1 else "error"


def limpiar_frase(texto: str, maximo: int = MAX_FRASE) -> str:
    """Una línea, sin URLs ni saltos, recortada para una burbuja.

    El host de OpenPets valida la longitud y rechaza mensajes con formato
    raro; además, un aviso con una URL o un salto de línea se ve mal en la
    mascota. Nunca lanza: el avatar no puede tumbar al motor.
    """
    limpio = " ".join(str(texto or "").split())
    limpio = re.sub(r"https?://\S+", "", limpio).strip()
    if len(limpio) > maximo:
        limpio = limpio[: maximo - 1].rstrip() + "…"
    return limpio
