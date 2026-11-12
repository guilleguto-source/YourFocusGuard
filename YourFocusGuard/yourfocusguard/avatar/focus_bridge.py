"""OpenPets Focus Bridge — capacidades del Pet Assistant (v0.7.0, Fase 3).

Este módulo expone, sobre el IPC existente de OpenPets (hello / pet.react /
pet.say), las capacidades que el Pet Assistant puede invocar:

    * focus.start_session  — inicia una sesión de trabajo con apps y tarea
    * focus.pause          — pausa/reanuda el agente
    * focus.status         — devuelve el estado actual (FOCO, PAUSA, ESCALADA…)
    * focus.concentracion  — activa/desactiva el modo máxima concentración

No hay TypeScript: el puente habla el mismo protocolo JSON de una línea que
ya usa AvatarOpenPets, reutilizando ``peticion`` y el descubrimiento de
ipc.json. El motor de YourFocusGuard lo integra como una capa delgada sobre
GuardianSesion, Agent y ModoConcentracion.

Las respuestas van como burbujas de OpenPets (pet.say) para que el usuario
las vea en su mascota sin salir del flujo.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from yourfocusguard.actions.concentracion import ModoConcentracion, crear_modo_concentracion
from yourfocusguard.avatar.base import limpiar_frase
from yourfocusguard.avatar.openpets import peticion
from yourfocusguard.config import Config
from yourfocusguard.session_guard import GuardianSesion

log = logging.getLogger(__name__)

#: Métodos que el Pet Assistant puede invocar por el IPC de OpenPets.
METODOS_FOCUS = (
    "focus.start_session",
    "focus.pause",
    "focus.resume",
    "focus.status",
    "focus.concentracion",
    "focus.sigo",
)


class FocusBridge:
    """Puente entre el Pet Assistant de OpenPets y el agente YourFocusGuard.

    Cada invocación llega como una petición OpenPets con method en
    METODOS_FOCUS y params con los argumentos. El puente ejecuta la acción
    sobre el motor y responde con pet.say (burbuja) para que el usuario la
    vea en su mascota.
    """

    def __init__(
        self,
        cfg: Config,
        sesion: GuardianSesion,
        agente_ref: Callable[[], Any] | None = None,
        discovery: dict | None = None,
        enviar: Callable[[dict | None, str, dict | None], Any] | None = None,
        reloj: Callable[[], float] = time.time,
    ) -> None:
        self.cfg = cfg
        self.sesion = sesion
        self._agente_ref = agente_ref
        self._enviar = enviar or peticion
        self._discovery = discovery
        self._reloj = reloj
        self._concentracion: ModoConcentracion | None = None
        self._activo = False

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #

    def iniciar(self) -> bool:
        """Comprueba que OpenPets responde y marca el puente como activo."""
        try:
            self._enviar(self._discovery, "hello", {})
        except Exception as exc:
            log.info("Focus Bridge: OpenPets no disponible (%s)", exc)
            return False
        self._activo = True
        self._concentracion = crear_modo_concentracion(self.cfg.concentracion)
        log.info("Focus Bridge conectado a OpenPets")
        return True

    def parar(self) -> None:
        self._activo = False
        if self._concentracion is not None and self._concentracion.activo:
            self._concentracion.desactivar()

    def disponible(self) -> bool:
        return self._activo

    # ------------------------------------------------------------------ #
    # Despacho de peticiones del Pet Assistant
    # ------------------------------------------------------------------ #

    def manejar(self, method: str, params: dict | None) -> dict[str, Any]:
        """Ejecuta un comando focus.* y devuelve el resultado para OpenPets."""
        params = params or {}
        if not self._activo:
            return {"ok": False, "error": {"code": "bridge_no_disponible", "message": "OpenPets no conectado"}}

        try:
            if method == "focus.start_session":
                return self._cmd_start_session(params)
            if method == "focus.pause":
                return self._cmd_pause(params)
            if method == "focus.resume":
                return self._cmd_resume(params)
            if method == "focus.status":
                return self._cmd_status(params)
            if method == "focus.concentracion":
                return self._cmd_concentracion(params)
            if method == "focus.sigo":
                return self._cmd_sigo(params)
            return {"ok": False, "error": {"code": "metodo_desconocido", "message": method}}
        except Exception as exc:  # nunca dejar caer al puente
            log.exception("Focus Bridge error en %s", method)
            return {"ok": False, "error": {"code": "interno", "message": str(exc)[:200]}}

    # ------------------------------------------------------------------ #
    # Comandos individuales
    # ------------------------------------------------------------------ #

    def _cmd_start_session(self, params: dict) -> dict[str, Any]:
        texto = str(params.get("texto") or "sesión de trabajo").strip()
        apps = [str(a).strip().lower() for a in (params.get("apps") or []) if str(a).strip()]
        aux = [str(a).strip().lower() for a in (params.get("aux") or []) if str(a).strip()]
        minutos = float(params.get("minutos") or 0)

        ahora = self._reloj()
        self.sesion.iniciar(ahora, apps, apps_aux=aux, minutos=minutos or None)

        # Si el modo concentración está configurado, activarlo también
        if self.cfg.concentracion.habilitado and self._concentracion is not None:
            self._concentracion.activar()

        frase = limpiar_frase(
            f"Sesión iniciada: {texto}. Apps: {', '.join(apps) or 'solo inactividad'}."
        )
        self._decir(frase)
        return {
            "ok": True,
            "result": {
                "sesion": "activa",
                "tarea": texto,
                "apps": apps,
                "auxiliares": aux,
                "minutos": minutos or 0,
            },
        }

    def _cmd_pause(self, params: dict) -> dict[str, Any]:
        minutos = float(params.get("minutos") or self.cfg.privacidad.pausa_rapida_min)
        agente = self._obtener_agente()
        if agente is not None and hasattr(agente, "paused_until"):
            agente.paused_until = ahora = self._reloj() + minutos * 60
        frase = limpiar_frase(f"Pausa de {int(minutos)} min. ¡Descansa!")
        self._decir(frase)
        return {"ok": True, "result": {"pausa": True, "minutos": minutos}}

    def _cmd_resume(self, params: dict) -> dict[str, Any]:
        agente = self._obtener_agente()
        if agente is not None and hasattr(agente, "paused_until"):
            agente.paused_until = None
        frase = limpiar_frase("Reanudado. Vuelta al foco.")
        self._decir(frase)
        return {"ok": True, "result": {"pausa": False}}

    def _cmd_status(self, params: dict) -> dict[str, Any]:
        agente = self._obtener_agente()
        estado = "desconocido"
        tarea = ""
        sesion_activa = self.sesion.activa
        if agente is not None:
            estado = agente.estado.value
            tarea = agente.tarea or ""
        return {
            "ok": True,
            "result": {
                "estado": estado,
                "tarea": tarea,
                "sesion_activa": sesion_activa,
                "apps": list(self.sesion.apps),
                "concentracion": (
                    self._concentracion.activo if self._concentracion is not None else False
                ),
            },
        }

    def _cmd_concentracion(self, params: dict) -> dict[str, Any]:
        activar = bool(params.get("activar", True))
        if self._concentracion is None:
            self._concentracion = crear_modo_concentracion(self.cfg.concentracion)
        if activar:
            resumen = self._concentracion.activar()
            frase = limpiar_frase(
                "Modo máxima concentración activado: dominios y audio bloqueados."
            )
        else:
            resumen = self._concentracion.desactivar()
            frase = limpiar_frase("Modo máxima concentración desactivado. Todo restaurado.")
        self._decir(frase)
        return {
            "ok": True,
            "result": {"concentracion": activar, "detalle": resumen},
        }

    def _cmd_sigo(self, params: dict) -> dict[str, Any]:
        agente = self._obtener_agente()
        if agente is not None and hasattr(agente, "confirmar_sigo"):
            ahora = self._reloj()
            agente.confirmar_sigo(ahora)
        frase = limpiar_frase("Vale, sigo contigo. A la tarea.")
        self._decir(frase)
        return {"ok": True, "result": {"sigo": True}}

    # ------------------------------------------------------------------ #
    # Salida (burbuja de OpenPets)
    # ------------------------------------------------------------------ #

    def _decir(self, frase: str) -> None:
        """Envía la frase como burbuja de OpenPets (pet.say)."""
        if not frase:
            return
        try:
            self._enviar(
                self._discovery,
                "pet.say",
                {"message": frase, "reaction": "thinking"},
            )
        except Exception as exc:
            log.debug("Focus Bridge: no se pudo enviar burbuja: %s", exc)

    # ------------------------------------------------------------------ #
    # Referencia al agente (inyectable desde el motor)
    # ------------------------------------------------------------------ #

    def _obtener_agente(self) -> Any | None:
        if self._agente_ref is not None:
            try:
                return self._agente_ref()
            except Exception:
                return None
        return None


def crear_focus_bridge(
    cfg: Config,
    sesion: GuardianSesion,
    agente_ref: Callable[[], Any] | None = None,
    discovery: dict | None = None,
) -> FocusBridge:
    """Fábrica: devuelve un FocusBridge listo."""
    return FocusBridge(cfg, sesion, agente_ref=agente_ref, discovery=discovery)
