"""Tests para el avatar embebido y los endpoints de mascota en panel.py (v0.8.0)."""
import json
from unittest.mock import MagicMock

from yourfocusguard.avatar.embed import AvatarEmbed
from yourfocusguard.panel import (
    pet_decir,
    pet_estado_actual,
    pet_fijar_mascota,
    pet_fijar_reaccion,
    pet_registrar_respuesta,
    pet_consumir_respuestas,
)


def test_pet_state_basico():
    pet_fijar_mascota("bitty")
    pet_fijar_reaccion("working")
    estado = pet_estado_actual()
    assert estado["mascota"] == "bitty"
    assert estado["reaccion"] == "working"


def test_pet_decir_y_responder():
    pet_decir("¿Sigue en la tarea?", reaccion="thinking", opciones=["Sí", "No"], duracion_ms=3000)
    estado = pet_estado_actual()
    assert estado["burbuja"]["texto"] == "¿Sigue en la tarea?"
    assert estado["burbuja"]["opciones"] == ["Sí", "No"]
    assert estado["reaccion"] == "thinking"

    pet_registrar_respuesta("Sí")
    res = pet_consumir_respuestas()
    assert res == ["Sí"]
    assert pet_consumir_respuestas() == []


def test_avatar_embed_protocolo():
    cfg = MagicMock()
    cfg.avatar.frases = True
    cfg.avatar.mascota = "shadow-kit"

    avatar = AvatarEmbed(cfg)
    assert avatar.iniciar() is True
    assert avatar.disponible is True

    avatar.fijar_estado("FOCO")
    estado = pet_estado_actual()
    assert estado["reaccion"] == "working"

    avatar.al_alerta(2, "¡Alerta de prueba!")
    estado = pet_estado_actual()
    assert estado["reaccion"] == "error"
    assert "¡Alerta de prueba!" in estado["burbuja"]["texto"]

    avatar.preguntar("¿Esto es parte del flujo?", opciones=["Sí", "No"])
    estado = pet_estado_actual()
    assert estado["burbuja"]["opciones"] == ["Sí", "No"]

    avatar.parar()
    assert avatar.disponible is False
