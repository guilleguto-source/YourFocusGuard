"""Grupos de flujo de trabajo y detector de descubrimiento inteligente (v0.8.0).

Permite que las apps relacionadas a una tarea principal (ej: Gutoflow al editar fotos,
o VSCode al programar) sean reconocidas como parte del flujo sin disparar alertas prematuras.
Además, detecta si el usuario pasa más de cierto umbral en una app no catalogada y
hace la pregunta amable para sumarla al flujo de trabajo automáticamente.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

log = logging.getLogger(__name__)


@dataclass
class GrupoFlujo:
    nombre: str
    apps: list[str]
    apps_relacionadas: list[str] = field(default_factory=list)
    tolerancia_seg: float = 120.0  # 2 minutos por defecto
    mensaje_aviso: str = ""

    def __post_init__(self) -> None:
        self._patrones_apps = [re.compile(re.escape(a.strip().lower())) for a in self.apps if a.strip()]
        self._patrones_rel = [re.compile(re.escape(a.strip().lower())) for a in self.apps_relacionadas if a.strip()]

    def matchea_principal(self, app: str | None) -> bool:
        if not app or not self._patrones_apps:
            return False
        app_l = app.lower()
        return any(p.search(app_l) for p in self._patrones_apps)

    def matchea_relacionada(self, app: str | None) -> bool:
        if not app or not self._patrones_rel:
            return False
        app_l = app.lower()
        return any(p.search(app_l) for p in self._patrones_rel)


@dataclass
class VeredictoFlujo:
    es_relacionada: bool
    grupo: GrupoFlujo | None = None
    segundos_en_relacionada: float = 0.0
    supera_tolerancia: bool = False
    mensaje: str = ""


class GestorFlujos:
    """Gestiona la pertenencia a flujos y los tiempos en apps relacionadas."""

    def __init__(self, grupos: Iterable[GrupoFlujo] = ()) -> None:
        self.grupos: list[GrupoFlujo] = list(grupos)
        self._app_relacionada_actual: str | None = None
        self._inicio_relacionada: float | None = None

    def buscar_grupo_para_sesion(self, apps_sesion: Iterable[str]) -> GrupoFlujo | None:
        """Encuentra el grupo de flujo que mejor encaje con las apps de la sesión activa."""
        apps_norm = {a.strip().lower() for a in apps_sesion if a and a.strip()}
        for grupo in self.grupos:
            for g_app in grupo.apps:
                if any(g_app in s_app or s_app in g_app for s_app in apps_norm):
                    return grupo
        return None

    def evaluar(
        self,
        app_actual: str | None,
        grupo_activo: GrupoFlujo | None,
        ahora: float,
    ) -> VeredictoFlujo:
        """Evalúa si la ventana al frente es una app relacionada del grupo activo."""
        if not app_actual or not grupo_activo:
            self._limpiar_relacionada()
            return VeredictoFlujo(es_relacionada=False)

        if not grupo_activo.matchea_relacionada(app_actual):
            self._limpiar_relacionada()
            return VeredictoFlujo(es_relacionada=False)

        app_norm = app_actual.strip().lower()
        if self._app_relacionada_actual != app_norm or self._inicio_relacionada is None:
            self._app_relacionada_actual = app_norm
            self._inicio_relacionada = ahora

        transcurrido = max(0.0, ahora - self._inicio_relacionada)
        supera = transcurrido >= grupo_activo.tolerancia_seg
        mensaje = grupo_activo.mensaje_aviso or f"Llevas un rato en {app_actual}. ¿Volvemos a la tarea?"

        return VeredictoFlujo(
            es_relacionada=True,
            grupo=grupo_activo,
            segundos_en_relacionada=transcurrido,
            supera_tolerancia=supera,
            mensaje=mensaje if supera else "",
        )

    def _limpiar_relacionada(self) -> None:
        self._app_relacionada_actual = None
        self._inicio_relacionada = None


@dataclass
class EventoDescubrimiento:
    app: str
    grupo_nombre: str
    segundos: float
    pregunta: str
    opciones: list[str]


class DetectorDescubrimiento:
    """Detecta apps no clasificadas durante una sesión y genera la pregunta inteligente."""

    def __init__(
        self,
        umbral_seg: float = 120.0,
        cooldown_seg: float = 1800.0,  # 30 minutos sin volver a preguntar por la misma app
    ) -> None:
        self.umbral_seg = umbral_seg
        self.cooldown_seg = cooldown_seg
        self._app_en_observacion: str | None = None
        self._inicio_observacion: float | None = None
        self._preguntadas: dict[str, float] = {}  # app -> timestamp de última pregunta

    def evaluar(
        self,
        app_actual: str | None,
        grupo_activo: GrupoFlujo | None,
        ahora: float,
    ) -> EventoDescubrimiento | None:
        if not app_actual or not grupo_activo:
            self._app_en_observacion = None
            self._inicio_observacion = None
            return None

        app_norm = app_actual.strip().lower()

        # Si ya es app principal o relacionada, no hay nada que descubrir
        if grupo_activo.matchea_principal(app_norm) or grupo_activo.matchea_relacionada(app_norm):
            self._app_en_observacion = None
            self._inicio_observacion = None
            return None

        # Si ya preguntamos recientemente por esta app, respetar cooldown
        ultimo = self._preguntadas.get(app_norm)
        if ultimo and (ahora - ultimo) < self.cooldown_seg:
            return None

        if self._app_en_observacion != app_norm or self._inicio_observacion is None:
            self._app_en_observacion = app_norm
            self._inicio_observacion = ahora

        tiempo = ahora - self._inicio_observacion
        if tiempo >= self.umbral_seg:
            self._preguntadas[app_norm] = ahora
            self._app_en_observacion = None
            self._inicio_observacion = None

            minutos = max(1, round(tiempo / 60))
            pregunta = (
                f"He visto que estás {minutos} min en {app_actual} mientras trabajas en "
                f"{grupo_activo.nombre}. ¿Forma parte de tu flujo de trabajo?"
            )
            return EventoDescubrimiento(
                app=app_norm,
                grupo_nombre=grupo_activo.nombre,
                segundos=tiempo,
                pregunta=pregunta,
                opciones=["Sí, agrégala", "No, es distracción", "Preguntar luego"],
            )

        return None
