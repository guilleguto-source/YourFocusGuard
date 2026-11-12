"""Despachador de eventos en memoria (Pub/Sub) para desacoplar capas (v0.8.2).

Permite que las capas de bajo nivel (actions, capture) emitan eventos sin
importar componentes de interfaz (panel web, ventana flotante).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

log = logging.getLogger(__name__)

# Eventos estándar
EVT_PET_SAY = "pet.say"
EVT_PET_REACTION = "pet.reaction"
EVT_PET_SET = "pet.set"
EVT_USER_VOICE_RESPONSE = "user.voice_response"
EVT_CONSUMO_API = "api.consumo"

_SUBSCRIBERS: dict[str, list[Callable[[Any], None]]] = defaultdict(list)


def subscribe(event_type: str, handler: Callable[[Any], None]) -> None:
    """Registra una función oyente para un tipo de evento."""
    if handler not in _SUBSCRIBERS[event_type]:
        _SUBSCRIBERS[event_type].append(handler)


def unsubscribe(event_type: str, handler: Callable[[Any], None]) -> None:
    """Elimina la función oyente."""
    if handler in _SUBSCRIBERS[event_type]:
        _SUBSCRIBERS[event_type].remove(handler)


def publish(event_type: str, data: Any = None) -> None:
    """Notifica a todos los oyentes de forma segura."""
    for handler in list(_SUBSCRIBERS.get(event_type, [])):
        try:
            handler(data)
        except Exception as exc:
            log.debug("Error en manejador de evento %s: %s", event_type, exc)
