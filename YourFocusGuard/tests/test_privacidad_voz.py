"""Tests de regresión de privacidad de la voz (v0.8.3).

Contexto: en v0.8.2 el candado "modo privado ⇒ cero micrófono y cero nube"
existía pero leía atributos equivocados (cfg.agente.modo_privado no existe en
AgenteCfg; getattr(self, "modo_privado") nunca se asignaba en el engine), con
lo que el microseguimiento automático seguía enviando audio/texto a Groq aun
con el modo privado activado. Estos tests aseguran que los tres caminos de voz
respetan la bandera real: cfg.modo_privado.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

import yourfocusguard.actions.groq_voice as groq_voice
import yourfocusguard.actions.tts as tts_mod
from yourfocusguard.actions.notifier import Notifier
from yourfocusguard.core import events


class _HiloSincrono:
    """Sustituye threading.Thread para ejecutar el trabajo al instante."""

    def __init__(self, target=None, name=None, daemon=None, **_kw):
        self._target = target

    def start(self) -> None:
        if self._target:
            self._target()


@pytest.fixture()
def _silenciar_tts(monkeypatch):
    """El TTS es local (no fuga a la nube), pero se apaga para no ruido de hilo."""
    llamadas: list[str] = []
    monkeypatch.setattr(tts_mod, "speak", lambda texto: llamadas.append(texto))
    monkeypatch.setattr(tts_mod, "is_speaking", lambda: False)
    return llamadas


# --------------------------------------------------------------------------- #
# 1. Escucha automática tras aviso N3 (Notifier.voz -> AsistenteVozGroq)
# --------------------------------------------------------------------------- #

def test_n3_modo_privado_no_abre_micro(monkeypatch, cfg, _silenciar_tts):
    """Con modo privado, Notifier.voz NO construye el oyente ni abre el micro."""
    cfg.modo_privado = True
    construidos: list[object] = []

    class _OyenteFalso:
        def __init__(self, callback_respuesta=None):
            construidos.append(self)

        def escuchar_y_procesar_async(self, *a, **kw):
            construidos.append("escucha")

    monkeypatch.setattr(groq_voice, "obtener_api_key_groq", lambda: "gsk_test_x")
    monkeypatch.setattr(groq_voice, "AsistenteVozGroq", _OyenteFalso)

    Notifier(cfg, consola=False).voz("¿Sigues en la tarea?")

    assert construidos == [], "el modo privado no debe iniciar ninguna escucha"


def test_n3_sin_modo_privado_si_abre_escucha(monkeypatch, cfg, _silenciar_tts):
    """Sin modo privado (y con clave Groq), la escucha automática sigue existiendo."""
    cfg.modo_privado = False
    escuchas: list[dict] = []

    class _OyenteFalso:
        def __init__(self, callback_respuesta=None):
            self.callback = callback_respuesta

        def escuchar_y_procesar_async(self, **kw):
            escuchas.append(kw)

    monkeypatch.setattr(groq_voice, "obtener_api_key_groq", lambda: "gsk_test_x")
    monkeypatch.setattr(groq_voice, "AsistenteVozGroq", _OyenteFalso)

    Notifier(cfg, consola=False).voz("¿Sigues en la tarea?")

    assert len(escuchas) == 1
    assert escuchas[0]["opciones"] == ["Sigo en la tarea", "Pausar 15 min", "Sí", "No"]


def test_n3_sin_clave_groq_no_escucha_nada(monkeypatch, cfg, _silenciar_tts):
    """Sin GROQ_API_KEY no hay nube posible: no se construye oyente."""
    cfg.modo_privado = False
    construidos: list[object] = []

    class _OyenteFalso:
        def __init__(self, *a, **kw):
            construidos.append(self)

    monkeypatch.setattr(groq_voice, "obtener_api_key_groq", lambda: "")
    monkeypatch.setattr(groq_voice, "AsistenteVozGroq", _OyenteFalso)

    Notifier(cfg, consola=False).voz("hola")

    assert construidos == []


# --------------------------------------------------------------------------- #
# 2. Botón 🎤 de la mascota (hablar_con_mascota_async)
# --------------------------------------------------------------------------- #

def test_hablar_mascota_modo_privado_no_graba_audio(monkeypatch, _silenciar_tts):
    """Con modo privado no se abre el micrófono y se avisa por burbuja."""
    monkeypatch.setattr(groq_voice.threading, "Thread", _HiloSincrono)
    grabaciones: list[float] = []
    monkeypatch.setattr(
        groq_voice, "grabar_audio", lambda segundos=8.0: grabaciones.append(segundos)
    )

    dichos: list[dict] = []
    events.subscribe(events.EVT_PET_SAY, lambda d: dichos.append(d))
    try:
        groq_voice.hablar_con_mascota_async(segundos=0.2, modo_privado=True)
    finally:
        events.unsubscribe(events.EVT_PET_SAY, lambda d: dichos.append(d))

    assert grabaciones == [], "el micrófono debe permanecer cerrado en modo privado"
    assert any("modo privado" in str(d.get("texto", "")).lower() for d in dichos), (
        "la mascota debe informar por burbuja que el modo privado está activo"
    )


def test_hablar_mascota_sin_modo_privado_abre_micro(monkeypatch, _silenciar_tts):
    """Sin modo privado el flujo es el de siempre (aquí: micro abierto, silencio)."""
    monkeypatch.setattr(groq_voice.threading, "Thread", _HiloSincrono)
    grabaciones: list[float] = []
    monkeypatch.setattr(
        groq_voice, "grabar_audio", lambda segundos=8.0: grabaciones.append(segundos)
    )

    groq_voice.hablar_con_mascota_async(segundos=0.2, modo_privado=False)

    assert len(grabaciones) == 1


def test_conversar_muse_modo_privado_no_llama_nube(monkeypatch, _silenciar_tts):
    """Defensa en profundidad: conversar_con_muse con privado nunca abre socket."""
    abiertos: list[str] = []

    def _urlopen_falso(req, timeout=None):
        abiertos.append(getattr(req, "full_url", str(req)))
        raise AssertionError("no debe contactarse a la nube en modo privado")

    monkeypatch.setattr(groq_voice.urllib.request, "urlopen", _urlopen_falso)
    monkeypatch.setattr(groq_voice, "obtener_endpoint_llm_local", lambda: None)

    respuesta = groq_voice.conversar_con_muse("estoy abrumado", modo_privado=True)

    assert abiertos == []
    assert "modo privado" in respuesta.lower() or "silencio" in respuesta.lower()


# --------------------------------------------------------------------------- #
# 3. Guardas estructurales: que el candado lea SIEMPRE cfg.modo_privado
# --------------------------------------------------------------------------- #

def test_candados_modo_privado_leen_la_bandera_real():
    """Regresión v0.8.3: nadie vuelve a leer atributos fantasma de modo privado.

    El bug original era getattr(self.cfg.agente, "modo_privado") en Notifier
    (AgenteCfg no tiene ese campo) y getattr(self, "modo_privado") en el engine
    (atributo nunca asignado). Esta guarda de fuente evita reintroducirlos.
    """
    raiz = Path(groq_voice.__file__).resolve().parents[2]  # carpeta del proyecto
    fuente_notifier = (raiz / "yourfocusguard" / "actions" / "notifier.py").read_text(
        encoding="utf-8"
    )
    fuente_engine = (raiz / "yourfocusguard" / "engine.py").read_text(encoding="utf-8")

    assert 'getattr(self.cfg.agente, "modo_privado"' not in fuente_notifier, (
        "Notifier debe leer cfg.modo_privado, no cfg.agente.modo_privado "
        "(atributo inexistente en AgenteCfg)"
    )
    assert 'getattr(self, "modo_privado"' not in fuente_engine, (
        "El engine debe leer self.cfg.modo_privado, no un atributo propio "
        "que nunca se asigna"
    )
