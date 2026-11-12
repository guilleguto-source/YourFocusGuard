"""Nivel B: heurística local degradada (blueprint, cap. 4).

Sin red neuronal: clasifica la app activa y el título de ventana contra las
listas configurables, usa el frame anterior para exigir continuidad (regla 1
anti-falso-positivo) y emite el mismo veredicto JSON que la nube, con
confianza más baja. Inspirada en ActivityWatch (Apéndice A).

Tabla de confianzas (deliberadamente conservadora):
  * distraccion en 2 frames seguidos -> desvio 0.85 (autoritario)
  * distraccion en 1 frame solo      -> desvio 0.55 (debil: transicion breve)
  * app/titulo de enfoque            -> continuidad 0.75 (autoritario)
  * app neutra o desconocida         -> continuidad 0.35 / 0.25 (debil)
Los veredictos debiles no cambian el estado del motor: solo informan.
"""
from __future__ import annotations

import re

from yourfocusguard.brain.base import Brain, Verdict
from yourfocusguard.config import Config
from yourfocusguard.constants import ORIGEN_HEURISTICA
from yourfocusguard.memory.fifo import FrameBuffer
from yourfocusguard.memory.models import FrameSnapshot

# Palabras que convierten una coincidencia en motivo "video" o "redes".
_PALABRAS_VIDEO = (
    "youtube", "netflix", "twitch", "disney", "hbo", "crunchyroll",
    "prime video", "mundonick", "pluto", "flow", "youtube music",
)
_PALABRAS_REDES = (
    "tiktok", "instagram", "facebook", "twitter", "x.com", "reddit",
    "pinterest", "9gag", "discord", "telegram", "whatsapp web", "threads",
)


def _norm(texto: str | None) -> str:
    return (texto or "").strip().lower()


def _match_cualquiera(texto: str, patrones: list[str]) -> str | None:
    """Devuelve el patrón que coincide (apps: subcadena; títulos: regex)."""
    for patron in patrones:
        patron = patron.strip()
        if not patron:
            continue
        if patron in texto:
            return patron
    return None


def _match_regex(texto: str, patrones: list[str]) -> str | None:
    for patron in patrones:
        patron = patron.strip()
        if not patron:
            continue
        try:
            if re.search(patron, texto, re.IGNORECASE):
                return patron
        except re.error:
            # patrón inválido del usuario: caer a subcadena, sin romper el agente
            if patron in texto:
                return patron
    return None


def motivo_desde_patron(patron: str) -> str:
    """Clasifica el patrón que disparó la distracción en el vocabulario del prompt."""
    p = patron.lower()
    if any(palabra in p for palabra in _PALABRAS_VIDEO):
        return "video"
    if any(palabra in p for palabra in _PALABRAS_REDES):
        return "redes"
    return "otro"


class HeuristicBrain(Brain):
    """Nivel B: coste casi nulo, cero red, misma interfaz que la nube."""

    name = "heuristica"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # ------------------------------------------------------------------ #

    def classify(self, snap: FrameSnapshot) -> str:
        """enfoque | distraccion | neutra | desconocida (sin tocar exclusiones)."""
        cfg = self.cfg.heuristica
        app = _norm(snap.app)
        titulo = _norm(snap.title)

        if app and _match_cualquiera(app, cfg.apps_distraccion):
            return "distraccion"
        if titulo and _match_regex(titulo, cfg.titulos_distraccion):
            return "distraccion"
        if app and _match_cualquiera(app, cfg.apps_enfoque):
            return "enfoque"
        if titulo and _match_regex(titulo, cfg.titulos_enfoque):
            return "enfoque"
        if app and _match_cualquiera(app, cfg.apps_neutras):
            return "neutra"
        return "desconocida"

    def analyze(self, buffer: FrameBuffer, tarea: str = "") -> Verdict:
        import time

        ultimo = buffer.latest()
        if ultimo is None:
            return Verdict(
                continuidad=True, desvio=False, motivo="ninguno",
                app_detectada="", confianza=0.0, accion_sugerida="nada",
                origen=ORIGEN_HEURISTICA, ts=time.time(),
            )

        clase_actual = self.classify(ultimo)
        clase_previa = self.classify(buffer.previous()) if buffer.previous() else None
        app_txt = ultimo.app or ""

        if clase_actual == "distraccion":
            patron = self._patron_distraccion(ultimo)
            motivo = motivo_desde_patron(patron) if patron else "otro"
            if clase_previa == "distraccion":
                # dos frames seguidos: caso claro (blueprint, cap. 4)
                return Verdict(
                    continuidad=False, desvio=True, motivo=motivo,
                    app_detectada=app_txt, confianza=0.85,
                    accion_sugerida="aviso", origen=ORIGEN_HEURISTICA,
                    ts=ultimo.ts,
                )
            # un solo frame: transición breve, no cuenta como cambio de contexto
            return Verdict(
                continuidad=False, desvio=True, motivo=motivo,
                app_detectada=app_txt, confianza=0.55,
                accion_sugerida="nada", origen=ORIGEN_HEURISTICA, ts=ultimo.ts,
            )

        if clase_actual == "enfoque":
            return Verdict(
                continuidad=True, desvio=False, motivo="ninguno",
                app_detectada=app_txt, confianza=0.75, accion_sugerida="nada",
                origen=ORIGEN_HEURISTICA, ts=ultimo.ts,
            )

        confianza = 0.35 if clase_actual == "neutra" else 0.25
        return Verdict(
            continuidad=True, desvio=False, motivo="ninguno",
            app_detectada=app_txt, confianza=confianza,
            accion_sugerida="nada", origen=ORIGEN_HEURISTICA, ts=ultimo.ts,
        )

    def _patron_distraccion(self, snap: FrameSnapshot) -> str | None:
        cfg = self.cfg.heuristica
        app = _norm(snap.app)
        titulo = _norm(snap.title)
        return (
            _match_cualquiera(app, cfg.apps_distraccion)
            or _match_regex(titulo, cfg.titulos_distraccion)
        )
