"""Vigilante de prohibiciones: presupuestos diarios por primer plano (v0.3.0).

Propuesta del usuario para el panel: "no permitir YouTube 1 hora, o redes
sociales". Implementado como presupuesto diario por patrón:

    - Cada ciclo del agente (5-15 s) mira SOLO la ventana activa (proceso +
      título) — sin capturas, sin nube. Si matchea un patrón prohibido, los
      segundos transcurridos desde el ciclo anterior se acumulan en la tabla
      ``presupuesto`` (clave fecha+patrón, sobrevive reinicios).
    - Al alcanzar ``limite_min_dia``: toast una sola vez por patrón al día
      y, si ``bloqueo_activo``, la app se MINIMIZA cada vez que vuelve al
      primer plano hasta el día siguiente. Ese es el "no permitir".
    - Las ventanas excluidas de privacidad nunca se cuentan (el agente
      finge no estar ahí, igual que el resto del pipeline).

Lógica pura e inyectable (cfg + db + reloj); el motor decide qué hacer con
cada aviso y el bloqueo lo ejecuta actions/window_actions.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable

from yourfocusguard.config import Config, ProhibicionCfg

log = logging.getLogger(__name__)

#: Tope de segundos acumulables entre dos ciclos (evita contar huecos de
#: suspensión del equipo como si fueran tiempo de la app prohibida).
DELTOPE_SEG = 90


def _compilar(patron: str) -> re.Pattern:
    p = (patron or "").strip().lower()
    try:
        return re.compile(p)
    except re.error:
        return re.compile(re.escape(p))


@dataclass
class AvisoProhibicion:
    """Transición a presupuesto agotado (se avisa una vez por patrón al día)."""

    patron: str
    limite_min: int
    usado_min: float


class VigilanteProhibiciones:
    """Contador y reglas de las prohibiciones. Sin I/O propia."""

    def __init__(self, cfg: Config, db, reloj: Callable = time.time) -> None:
        self.cfg = cfg
        self.db = db
        self.reloj = reloj
        self._firma: tuple | None = None
        self._entradas: list[ProhibicionCfg] = []
        self._patrones: dict[str, re.Pattern] = {}
        self._excepciones: dict[str, list[re.Pattern]] = {}
        self._acumulado: dict[str, int] = {}
        self._excedidas: set[str] = set()
        self._ultimo_ts: float | None = None

    # ------------------------------------------------------------------ #

    def _sincronizar(self) -> None:
        """Relee [prohibiciones] si cambió (edición en vivo desde el panel)."""
        firma = self.cfg.prohibiciones.firma()
        if firma == self._firma:
            return
        self._firma = firma
        vistos: set[str] = set()
        entradas: list[ProhibicionCfg] = []
        for e in self.cfg.prohibiciones.lista:
            if not e.patron or e.patron in vistos:
                if e.patron and e.patron in vistos:
                    log.warning("prohibición duplicada %r: se ignora la repetida", e.patron)
                continue
            vistos.add(e.patron)
            entradas.append(e)
        self._entradas = entradas
        self._patrones = {e.patron: _compilar(e.patron) for e in entradas}
        # v0.4.0: excepciones por patrón ("youtube music" no cuenta para "youtube")
        self._excepciones = {
            e.patron: [_compilar(x) for x in e.excepciones] for e in entradas
        }
        self._acumulado = {}
        for e in entradas:
            usado = 0
            if self.db is not None:
                try:
                    usado = self.db.presupuesto_usado_hoy(e.patron)
                except Exception:
                    log.exception("no se pudo leer el presupuesto de %r", e.patron)
            self._acumulado[e.patron] = usado
        # Las que ya llegan agotadas de una corrida anterior no re-avisan
        # (en aquella corrida ya salió el toast); el panel las muestra llenas.
        self._excedidas = {
            e.patron for e in entradas
            if e.limite_min_dia * 60 <= self._acumulado.get(e.patron, 0)
        }

    def _matchea(self, patron: str, app, titulo) -> bool:
        rx = self._patrones.get(patron)
        if rx is None:
            return False
        if app and rx.search(str(app).lower()):
            return True
        return bool(titulo and rx.search(str(titulo).lower()))

    def _excepcion_aplica(self, patron: str, app, titulo) -> bool:
        """True si el título actual cae en una excepción (p. ej. música)."""
        for rx in self._excepciones.get(patron, ()):  # ya compiladas
            if titulo and rx.search(str(titulo).lower()):
                return True
            # una excepción también puede ser por proceso (p. ej. "spotify")
            if app and rx.search(str(app).lower()):
                return True
        return False

    # ------------------------------------------------------------------ #

    def tick(self, ahora: float, app, titulo) -> list[AvisoProhibicion]:
        """Acumula y devuelve las transiciones a presupuesto agotado."""
        self._sincronizar()
        if self._ultimo_ts is None:
            self._ultimo_ts = ahora  # el primer ciclo no cuenta tiempo muerto
        delta = max(0.0, min(DELTOPE_SEG, ahora - self._ultimo_ts))
        self._ultimo_ts = ahora
        if not self._entradas or delta <= 0:
            return []

        avisos: list[AvisoProhibicion] = []
        for e in self._entradas:
            if self._excepcion_aplica(e.patron, app, titulo):
                continue  # v0.4.0: música de YouTube sí, vídeos no
            if self._matchea(e.patron, app, titulo):
                self._acumulado[e.patron] = self._acumulado.get(e.patron, 0) + int(delta)
                if self.db is not None:
                    try:
                        self.db.presupuesto_sumar(e.patron, int(delta))
                    except Exception:
                        log.exception("no se pudo acumular el presupuesto de %r", e.patron)
            usado = self._acumulado.get(e.patron, 0)
            if e.limite_min_dia * 60 <= usado and e.patron not in self._excedidas:
                self._excedidas.add(e.patron)
                avisos.append(
                    AvisoProhibicion(e.patron, e.limite_min_dia, round(usado / 60.0, 1))
                )
        return avisos

    def debe_bloquear(self, app, titulo) -> ProhibicionCfg | None:
        """Entrada a minimizar ahora: agotada + bloqueo_activo + al frente."""
        self._sincronizar()
        for e in self._entradas:
            if not e.bloqueo_activo:
                continue
            if e.limite_min_dia * 60 > self._acumulado.get(e.patron, 0):
                continue
            if self._matchea(e.patron, app, titulo) and not self._excepcion_aplica(
                e.patron, app, titulo
            ):
                return e
        return None

    def resumen(self) -> dict[str, float]:
        """{patron: minutos usados hoy} para state.json y el panel."""
        self._sincronizar()
        return {
            e.patron: round(self._acumulado.get(e.patron, 0) / 60.0, 1)
            for e in self._entradas
        }
