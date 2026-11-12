"""Avatar del asistente (v0.6.0): OpenPets, mascota tkinter o ninguno.

El motor pide la cara a `crear_avatar(cfg)`; todo lo demás (reglas, escalera,
prohibiciones) es independiente de quién ponga la cara.
"""
from yourfocusguard.avatar.base import (  # noqa: F401
    Avatar,
    REACCIONES_OPENPETS,
    MAX_FRASE,
    limpiar_frase,
    reaccion_para_alerta,
    reaccion_para_estado,
)
from yourfocusguard.avatar.factory import crear_avatar  # noqa: F401

__all__ = [
    "Avatar",
    "REACCIONES_OPENPETS",
    "MAX_FRASE",
    "limpiar_frase",
    "reaccion_para_alerta",
    "reaccion_para_estado",
    "crear_avatar",
]
