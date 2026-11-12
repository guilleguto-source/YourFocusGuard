"""Notificador: consola + beep + toast + voz, con degradación silenciosa."""
from __future__ import annotations

import logging

from yourfocusguard.actions import sound, toast, tts
from yourfocusguard.config import Config

log = logging.getLogger(__name__)


class Notifier:
    """Punto único de salida de avisos; los tests lo sustituyen por fakes."""

    def __init__(self, cfg: Config, consola: bool = True) -> None:
        self.cfg = cfg
        self.consola = consola

    # ------------------------------------------------------------------ #

    def aviso(self, mensaje: str) -> None:
        """N1: aviso sutil = consola + sonido corto suave."""
        sound.beep_suave()
        self._linea(mensaje)

    def toast(self, titulo: str, mensaje: str) -> None:
        """N2: toast nativo de Windows; si falla, banner de consola."""
        if not self.cfg.alertas.toast_habilitado:
            log.info("toast deshabilitado en la configuración: %s | %s", titulo, mensaje)
            return
        if not toast.send_toast(titulo, mensaje):
            print()
            print(f"    === {titulo} ===")
            print(f"    {mensaje}")
            print()

    def voz(self, texto: str) -> None:
        """N3: voz TTS breve y activación opcional de escucha por voz (v0.8.1)."""
        if not self.cfg.alertas.tts_habilitado:
            log.info("TTS deshabilitado en la configuración: %s", texto)
            return
        tts.speak(texto)

        # Respetar modo privado: cero micrófono y cero nube si modo_privado está activo.
        # v0.8.3: la bandera real vive en cfg.modo_privado (nivel superior, la que
        # escriben load_config/--privado y CommandProcessor con el comando "privado").
        # Antes se leía cfg.agente.modo_privado, un atributo que NO existe en
        # AgenteCfg, con lo que este candado nunca cerraba (fuga de privacidad).
        if getattr(self.cfg, "modo_privado", False):
            log.info("Modo privado activo: omitiendo captura de voz hacia Groq")
            return

        # Si Groq está configurado, iniciar ventana de escucha breve tras hablar
        try:
            from yourfocusguard.actions.groq_voice import AsistenteVozGroq, obtener_api_key_groq
            if obtener_api_key_groq():
                from yourfocusguard.core.events import EVT_USER_VOICE_RESPONSE, publish
                oyente = AsistenteVozGroq(
                    callback_respuesta=lambda r: publish(EVT_USER_VOICE_RESPONSE, r)
                )
                segundos_n3 = float(getattr(getattr(self.cfg, "voz", None), "segundos_n3", 7.0))
                oyente.escuchar_y_procesar_async(
                    contexto_pregunta=texto,
                    opciones=["Sigo en la tarea", "Pausar 15 min", "Sí", "No"],
                    segundos=segundos_n3,
                )
        except Exception as exc:
            log.debug("No se pudo iniciar escucha automática por voz: %s", exc)


    def info(self, mensaje: str) -> None:
        """Mensajes de ciclo Pomodoro y transiciones (sin sonido)."""
        self._linea(mensaje)

    def cerrar(self) -> None:
        """Termina el hilo de voz (v0.5.0) al apagar el agente."""
        tts.parar()

    # ------------------------------------------------------------------ #

    def _linea(self, mensaje: str) -> None:
        if self.consola:
            print(f"    {mensaje}")
