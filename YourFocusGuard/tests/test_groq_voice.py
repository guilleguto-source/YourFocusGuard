"""Tests para el módulo de voz Groq (v0.8.0)."""
import io
import json
from unittest.mock import MagicMock, patch

from yourfocusguard.actions.groq_voice import (
    obtener_api_key_groq,
    transcribir_con_groq,
    clasificar_intencion_groq,
    clasificar_intencion_local,
    conversar_con_muse,
    consultar_llm_local,
    obtener_endpoint_llm_local,
    AsistenteVozGroq,
)


def test_obtener_api_key():
    with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test_123"}):
        assert obtener_api_key_groq() == "gsk_test_123"


def test_transcribir_con_groq():
    fake_response = io.BytesIO(json.dumps({"text": "sigo trabajando en Lightroom"}).encode("utf-8"))
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = fake_response
        texto = transcribir_con_groq(b"RIFFdummydata", api_key="gsk_test")
        assert texto == "sigo trabajando en Lightroom"


def test_clasificar_intencion_groq():
    fake_response = io.BytesIO(json.dumps({
        "choices": [{"message": {"content": "Sí, agrégala"}}]
    }).encode("utf-8"))

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = fake_response
        res = clasificar_intencion_groq(
            texto_usuario="claro que sí, es mi programa de fotos",
            contexto_pregunta="¿Forma parte de tu flujo?",
            opciones=["Sí, agrégala", "No, es distracción", "Preguntar luego"],
            api_key="gsk_test",
        )
        assert res == "Sí, agrégala"


def test_asistente_voz_asincrono():
    cb = MagicMock()
    asistente = AsistenteVozGroq(callback_respuesta=cb)

    with patch("yourfocusguard.actions.tts.is_speaking", return_value=False), \
         patch("yourfocusguard.actions.groq_voice.grabar_audio", return_value=b"audio"), \
         patch("yourfocusguard.actions.groq_voice.transcribir_con_groq", return_value="estoy en Lightroom"), \
         patch("yourfocusguard.actions.groq_voice.clasificar_intencion_groq", return_value="Sí"):
        
        final_cb = MagicMock()
        asistente.escuchar_y_procesar_async(
            contexto_pregunta="¿Sigues en la tarea?",
            opciones=["Sí", "No"],
            segundos=1.0,
            al_finalizar=final_cb,
        )
        if asistente._hilo:
            asistente._hilo.join(timeout=3.0)

        cb.assert_called_once_with("Sí")
        final_cb.assert_called_once_with("Sí")


def test_clasificar_intencion_local_0ms():
    opciones = ["Sigo en la tarea", "Pausar 15 min", "Preguntar luego"]
    assert clasificar_intencion_local("aquí sigo trabajando", opciones) == "Sigo en la tarea"
    assert clasificar_intencion_local("necesito un break o pausa", opciones) == "Pausar 15 min"
    assert clasificar_intencion_local("luego te respondo", opciones) == "Preguntar luego"
    assert clasificar_intencion_local("bla bla ruido", opciones) is None


def test_conversar_con_muse_modo_privado():
    res = conversar_con_muse("hola muse", modo_privado=True)
    assert "silencio" in res.lower() or "aquí estoy" in res.lower()


def test_local_llm_adapter():
    with patch.dict("os.environ", {"OLLAMA_HOST": "http://localhost:11434"}):
        assert obtener_endpoint_llm_local() == "http://localhost:11434/v1/chat/completions"

    fake_response = io.BytesIO(json.dumps({
        "choices": [{"message": {"content": "¡Vamos con todo!"}}]
    }).encode("utf-8"))

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = fake_response
        resp = consultar_llm_local([{"role": "user", "content": "hola"}], endpoint="http://localhost:11434/v1/chat/completions")
        assert resp == "¡Vamos con todo!"


def test_trazabilidad_consumo_api():
    from yourfocusguard.core.events import EVT_CONSUMO_API, subscribe, unsubscribe
    eventos = []
    def _oyente(datos):
        eventos.append(datos)

    subscribe(EVT_CONSUMO_API, _oyente)
    try:
        fake_response = io.BytesIO(json.dumps({"text": "hola"}).encode("utf-8"))
        with patch("urllib.request.urlopen") as mock_url:
            mock_url.return_value.__enter__.return_value = fake_response
            # 32000 bytes = 1.0 segundo de audio WAV
            transcribir_con_groq(b"x" * 32000, api_key="gsk_test")
        assert len(eventos) == 1
        assert eventos[0]["segundos_audio"] == 1.0
        assert eventos[0]["coste_estimado"] > 0
    finally:
        unsubscribe(EVT_CONSUMO_API, _oyente)
