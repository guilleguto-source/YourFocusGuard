"""Guardián de tarea ("Modo Sesión"): vigilancia por predicados, sin imágenes.

Propuesta del usuario (sprint 1, retrospectiva): en lugar de capturas
indiscriminadas cada 15 s, cuando declara una sesión de trabajo ("tengo que
terminar esta sesión de fotos") el agente vigila dos predicados baratos del
sistema operativo —ventana al frente / visible en algún monitor, e idle de
entrada— y solo si un predicado se rompe toma medidas. Mientras todo va
bien: CERO capturas, CERO nube, CERO imágenes. La evidencia (una captura hoy,
foto de webcam en F3) se toma únicamente al disparar una regla.

Reglas (umbrales en [sesion]):

    R1  fuera_de_app     ninguna app objetivo en primer plano NI visible en
                         ningún monitor, de forma continua, durante
                         ``segundos_fuera_app`` (60 s por defecto).
    R2  inactivo_en_app  hay app objetivo presente pero llevan
                         ``segundos_inactivo`` sin tocar ratón ni teclado
                         (60 s por defecto).

Tratamiento de ventanas especiales:
    - apps_auxiliares (explorador, Bridge, un reproductor de referencia...)
      y ventanas excluidas por privacidad cuentan como "presente" para R1:
      no disparan la alarma de ausencia.
    - sobre ventanas excluidas nunca se captura evidencia y R2 se ignora
      (el agente finge no estar ahí, igual que en el pipeline normal).

El guardián es lógica pura e inyectable: la detección Win32 vive en
capture/window_info.py y el motor decide qué hacer con cada evaluación.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from yourfocusguard.config import SesionCfg

log = logging.getLogger(__name__)

MOTIVO_FUERA = "fuera_de_app"
MOTIVO_INACTIVO = "inactivo_en_app"


class Presencia(str, Enum):
    """Dónde está el usuario respecto de las apps de la sesión."""

    EN_APP = "en_app"            # app objetivo en primer plano
    VISIBLE = "visible"          # app objetivo visible en algún monitor (multi-monitor)
    AUXILIAR = "auxiliar"        # app tolerada en primer plano (parte del flujo)
    RELACIONADA = "relacionada"  # v0.8.0: app de flujo extendido (ej. Gutoflow)
    EXCLUIDA = "excluida"        # ventana de privacidad: el agente finge no estar
    FUERA = "fuera"              # otra cosa al frente y ninguna objetivo visible



def _compilar(patrones: Iterable[str]) -> list[re.Pattern]:
    """Compila los nombres como fragmentos de regex (minúsculas).

    "photoshop" matchea "photoshop"; "light.?room" matchea "lightroomclassic".
    Un patrón inválido se trata como texto literal (nunca rompe la sesión).
    """
    compilados = []
    for p in patrones:
        p = (p or "").strip().lower()
        if not p:
            continue
        try:
            compilados.append(re.compile(p))
        except re.error:
            log.warning("patrón de sesión inválido %r: se usa como texto literal", p)
            compilados.append(re.compile(re.escape(p)))
    return compilados


@dataclass
class EvaluacionSesion:
    """Resultado de evaluar los predicados en un instante."""

    presencia: Presencia
    senal: str | None        # MOTIVO_FUERA / MOTIVO_INACTIVO / None
    sostenido_seg: float     # cuánto lleva violándose la regla que disparó
    idle_seg: float | None


class GuardianSesion:
    """Estado y reglas del modo sesión. Sin I/O: todo viene inyectado."""

    def __init__(self, cfg: SesionCfg, reloj=time.time) -> None:
        self.cfg = cfg
        self.reloj = reloj
        self.activa = False
        self.apps: list[str] = []
        self.apps_aux: list[str] = []
        self.fin: float | None = None
        self.disparos = 0
        self.inicio = 0.0
        self.seg_en_app = 0.0
        self._ultimo_visto = 0.0
        self._ultima_eval: float | None = None
        self._ultima_presencia: Presencia | None = None
        self._patrones: list[re.Pattern] = []
        self._patrones_aux: list[re.Pattern] = []

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #

    def iniciar(
        self,
        ahora: float,
        apps: Iterable[str],
        apps_aux: Iterable[str] = (),
        minutos: float | None = None,
    ) -> None:
        self.activa = True
        self.apps = [a.strip().lower() for a in apps if a and a.strip()]
        self.apps_aux = [a.strip().lower() for a in apps_aux if a and a.strip()]
        self.fin = ahora + minutos * 60 if minutos and minutos > 0 else None
        self.inicio = ahora
        self.disparos = 0
        self.seg_en_app = 0.0
        self._ultimo_visto = ahora
        self._ultima_eval = None
        self._ultima_presencia = None
        self._patrones = _compilar(self.apps)
        self._patrones_aux = _compilar(self.apps_aux)

    def cerrar(self, ahora: float | None = None) -> dict:
        """Cierra la sesión y devuelve un resumen para el usuario."""
        ahora = self.reloj() if ahora is None else ahora
        self.activa = False
        return {
            "duracion_min": max(0.0, (ahora - self.inicio) / 60.0),
            "min_en_app": round(self.seg_en_app / 60.0, 1),
            "disparos": self.disparos,
        }

    def reconfigurar(
        self,
        ahora: float,
        apps: Iterable[str],
        apps_aux: Iterable[str] = (),
    ) -> bool:
        """Cambia las anclas en caliente (v0.5.0, panel/TOML en vivo).

        Devuelve True si algo cambió. El reloj de ausencia arranca de cero
        para no castigar el cambio de apps con un aviso inmediato.
        """
        nuevas = [a.strip().lower() for a in apps if a and a.strip()]
        nuevos_aux = [a.strip().lower() for a in apps_aux if a and a.strip()]
        if nuevas == self.apps and nuevos_aux == self.apps_aux:
            return False
        self.apps = nuevas
        self.apps_aux = nuevos_aux
        self._patrones = _compilar(nuevas)
        self._patrones_aux = _compilar(nuevos_aux)
        self._ultimo_visto = ahora
        return True

    def reanudar(self, ahora: float) -> None:
        """Tras una pausa (manual/Pomodoro): el reloj de ausencia vuelve a cero."""
        self._ultimo_visto = ahora
        self._ultima_eval = ahora

    # ------------------------------------------------------------------ #
    # Matcheo de apps
    # ------------------------------------------------------------------ #

    def matchea_objetivo(self, app: str | None) -> bool:
        return _matchea(self._patrones, app)

    def matchea_auxiliar(self, app: str | None) -> bool:
        return _matchea(self._patrones_aux, app)

    # ------------------------------------------------------------------ #
    # Evaluación
    # ------------------------------------------------------------------ #

    @property
    def ultimo_visto(self) -> float:
        """Última marca temporal con una app de la sesión presente."""
        return self._ultimo_visto

    def evaluar(
        self, ahora: float, presencia: Presencia, idle_seg: float | None
    ) -> EvaluacionSesion:
        """Aplica R1 y R2 sobre los predicados del tick actual."""
        presente = presencia != Presencia.FUERA

        # acumulado de tiempo "en la tarea" (para el resumen de cierre)
        if self._ultima_eval is not None and self._ultima_presencia != Presencia.FUERA:
            self.seg_en_app += max(0.0, ahora - self._ultima_eval)
        self._ultima_eval = ahora
        self._ultima_presencia = presencia

        if presente:
            self._ultimo_visto = ahora

        senal: str | None = None
        sostenido = 0.0

        # R1: fuera de las apps de la sesión durante N segundos continuos
        if self._patrones and presencia == Presencia.FUERA:
            fuera = ahora - self._ultimo_visto
            if fuera >= self.cfg.segundos_fuera_app:
                senal, sostenido = MOTIVO_FUERA, fuera

        # R2: sin tocar ratón ni teclado durante N segundos. Aplica aunque el
        # primer plano sea otra app: si hay apps declaradas R1 se evalúa antes
        # y gana (el motivo correcto es "fuera"), y sin apps declaradas esta
        # regla convierte la sesión en un vigilante genérico de congelamiento.
        if senal is None and idle_seg is not None:
            if idle_seg >= self.cfg.segundos_inactivo:
                senal, sostenido = MOTIVO_INACTIVO, idle_seg

        return EvaluacionSesion(
            presencia=presencia, senal=senal, sostenido_seg=sostenido, idle_seg=idle_seg
        )


def _matchea(patrones: list[re.Pattern], app: str | None) -> bool:
    if not app or not patrones:
        return False
    app = app.lower()
    return any(p.search(app) for p in patrones)
