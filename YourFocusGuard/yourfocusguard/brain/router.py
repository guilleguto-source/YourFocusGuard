"""Router del cerebro: nube cuando se puede, heurística local cuando no.

Políticas del blueprint que implementa:

* ciclo de análisis de nube (60 s en el PC, apagado en la laptop) y heurística
  B en cada captura intermedia (cap. 3-4);
* degradación transparente A -> B ante error, timeout, falta de clave o modo
  privado (cap. 4);
* disyuntor (circuit breaker): tras N fallos consecutivos la nube se apaga
  unos minutos en lugar de martillear la API;
* caché: si la app activa y el título no cambiaron y el último veredicto fue
  de continuidad, se reutiliza sin gastar (tabla 11);
* presupuesto diario con corte automático (tabla 11): al superar el tope de
  USD, la nube se silencia hasta el día siguiente.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import replace

from yourfocusguard.brain.base import Brain, BrainUnavailableError, Verdict
from yourfocusguard.brain.heuristic import HeuristicBrain
from yourfocusguard.config import Config
from yourfocusguard.constants import ORIGEN_CACHE
from yourfocusguard.memory.fifo import FrameBuffer

log = logging.getLogger(__name__)


class BrainRouter:
    """Decide quién analiza cada ciclo y degrada sin detener el agente."""

    def __init__(
        self,
        cfg: Config,
        local: HeuristicBrain | None = None,
        cloud: Brain | None = None,
        presupuesto=None,   # interface: presupuesto_hoy() -> float | None
        on_event=None,     # callback(tipo, motivo) para registrar en SQLite
        reloj=time.time,
    ) -> None:
        self.cfg = cfg
        self.local = local or HeuristicBrain(cfg)
        self.cloud = cloud
        self.presupuesto = presupuesto
        self.on_event = on_event or (lambda tipo, motivo: None)
        self.reloj = reloj

        # Disyuntor
        self._fallos = 0
        self._breaker_until = 0.0
        self._breaker_aviso = False

        # Caché y cadencia
        self._cache: tuple[tuple[str, str], Verdict, float] | None = None
        self._ultimo_nube_ts = 0.0

        # Presupuesto (aviso una sola vez por día de corte)
        self._presupuesto_aviso = False

    # ------------------------------------------------------------------ #
    # Estado para la consola
    # ------------------------------------------------------------------ #

    @property
    def nube_activa(self) -> bool:
        return self.cloud is not None and not self.cfg.modo_privado

    def _emitir(self, tipo: str, motivo: str) -> None:
        try:
            self.on_event(tipo, motivo)
        except Exception:  # nunca romper el ciclo por un log
            log.exception("on_event falló")

    # ------------------------------------------------------------------ #
    # Disyuntor
    # ------------------------------------------------------------------ #

    def _breaker_abierto(self, ahora: float) -> bool:
        if ahora < self._breaker_until:
            return True
        if self._breaker_until and ahora >= self._breaker_until:
            # media apertura: dejamos pasar el próximo intento
            self._breaker_until = 0.0
            self._fallos = max(0, self.cfg.cerebro.disyuntor_fallos - 1)
            self._breaker_aviso = False
        return False

    def _abrir_breaker(self, ahora: float) -> None:
        descanso = self.cfg.cerebro.disyuntor_descanso_min * 60
        self._breaker_until = ahora + descanso
        if not self._breaker_aviso:
            self._breaker_aviso = True
            self._emitir("cerebro", f"disyuntor_abierto:{self.cloud.name}")
            log.warning(
                "nube desactivada %d min tras %d fallos consecutivos",
                self.cfg.cerebro.disyuntor_descanso_min,
                self.cfg.cerebro.disyuntor_fallos,
            )

    # ------------------------------------------------------------------ #
    # Análisis
    # ------------------------------------------------------------------ #

    def analyze(self, buffer: FrameBuffer, tarea: str = "") -> Verdict:
        """Veredicto del ciclo actual, con el origen en ``verdict.origen``."""
        ahora = self.reloj()

        if self.cloud is None or self.cfg.modo_privado:
            return self.local.analyze(buffer, tarea)

        if self._breaker_abierto(ahora):
            return self.local.analyze(buffer, tarea)

        if self.presupuesto is not None:
            gastado = self.presupuesto.presupuesto_hoy()
            if gastado is not None and gastado >= self.cfg.cerebro.presupuesto_diario_usd:
                if not self._presupuesto_aviso:
                    self._presupuesto_aviso = True
                    self._emitir("cerebro", "presupuesto_agotado")
                    log.warning(
                        "presupuesto diario de nube agotado (%.2f USD): solo Nivel B hasta mañana",
                        gastado,
                    )
                return self.local.analyze(buffer, tarea)

        # ¿Toca análisis de nube? Entre ciclos, la heurística es gratis.
        cadencia = self.cfg.cerebro.analisis_nube_seg
        if self._ultimo_nube_ts and (ahora - self._ultimo_nube_ts) < cadencia:
            return self.local.analyze(buffer, tarea)

        ultimo = buffer.latest()
        if ultimo is None:  # FIFO sin frames todavía
            return self.local.analyze(buffer, tarea)
        clave = (ultimo.app or "", ultimo.title or "")

        # Caché: misma ventana, último veredicto de continuidad, aún fresco.
        if self._cache_aplicable(clave, ahora):
            cache_clave, veredicto, _ = self._cache
            self._ultimo_nube_ts = ahora
            return replace(veredicto, origen=ORIGEN_CACHE, ts=ahora)

        try:
            veredicto = self._llamar_nube_con_timeout(buffer, tarea)
        except BrainUnavailableError as exc:
            self._fallos += 1
            if self._fallos == 1:  # avisar solo del primer fallo consecutivo
                self._emitir("cerebro", f"fallback:{self.cloud.name}")
                log.warning("nube no disponible (%s); degradando al Nivel B", exc)
            if self._fallos >= self.cfg.cerebro.disyuntor_fallos:
                self._abrir_breaker(ahora)
            return self.local.analyze(buffer, tarea)

        # Éxito: cerrar disyuntor, contabilizar y refrescar caché.
        if self._breaker_aviso or self._fallos:
            log.info("nube recuperada (%s)", self.cloud.name)
        self._fallos = 0
        self._breaker_aviso = False
        self._ultimo_nube_ts = ahora
        self._cache = (clave, veredicto, ahora)
        self._presupuesto_aviso = False
        return veredicto

    def _cache_aplicable(self, clave: tuple[str, str], ahora: float) -> bool:
        if self._cache is None:
            return False
        cache_clave, veredicto, ts = self._cache
        frescor = self.cfg.cerebro.cache_min_seg * 60
        return (
            cache_clave == clave
            and (not veredicto.desvio)
            and (ahora - ts) < frescor
        )

    def _llamar_nube_con_timeout(
        self, buffer: FrameBuffer, tarea: str
    ) -> Verdict:
        """Llama a la nube con timeout; el hilo rezagado se ignora sin abortar."""
        timeout = self.cfg.cerebro.timeout_seg
        with ThreadPoolExecutor(max_workers=1) as pool:
            futuro = pool.submit(self.cloud.analyze, buffer, tarea)
            try:
                veredicto = futuro.result(timeout=timeout)
            except FutureTimeoutError as exc:
                raise BrainUnavailableError(
                    f"timeout de {timeout}s en {self.cloud.name}"
                ) from exc
        # Contabilizar el gasto después de una llamada exitosa.
        if self.presupuesto is not None:
            try:
                self.presupuesto.registrar_llamada_api(
                    self.cfg.cerebro.coste_por_analisis_usd
                )
            except Exception:
                log.exception("no se pudo registrar el consumo de API")
        return veredicto
