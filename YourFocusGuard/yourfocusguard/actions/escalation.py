"""Escalera de alertas gradual y no punitiva (tabla 5 del blueprint).

Tiempo t0 = primera señal autoritaria de desvío (no la confirmación):
la mascota puede anticiparse a los 20 s porque es reversible y sin sonido;
el resto de la escalera solo avanza si el desvío se sostiene.

    t+20 s  N0  mascota (expresión; en este MVP, línea de consola)
    t+30 s  N1  aviso sutil (consola + sonido corto suave)
    t+60 s  N2  toast urgente de Windows
    t+90 s  N3  voz TTS; después arranca el cooldown de 5 min

Si el desvío continúa tras el cooldown, puede abrirse un nuevo ciclo,
sujeto al tope de 4 escaladas por hora (protección anti-acoso).
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

from yourfocusguard.config import AlertasCfg
from yourfocusguard.constants import Accion

log = logging.getLogger(__name__)

MOTIVO_TEXTO = {
    "redes": "redes sociales",
    "video": "vídeo o streaming",
    "celular": "el celular en la mano",
    "conversacion": "una conversación",
    "mirada": "la mirada fuera de la pantalla",
    "fuera_de_app": "otra app (fuera de la sesión)",
    "inactivo_en_app": "inactividad",
    "otro": "otra cosa",
    "ninguno": "otra cosa",
}


@dataclass
class Alerta:
    """Una alerta lista para ejecutar por el motor."""

    nivel: int              # 0..3
    accion: Accion
    mensaje: str            # texto principal (consola / cuerpo del toast)
    titulo: str = ""        # título del toast (N2)
    texto_voz: str = ""     # frase hablada (N3)


def _minutos_txt(minutos: float) -> int:
    return max(1, int(round(minutos)))


@dataclass
class ResumenEpisodio:
    inicio: float
    fin: float
    niveles_disparados: list[int] = field(default_factory=list)

    @property
    def duracion_min(self) -> float:
        return (self.fin - self.inicio) / 60.0


class EscalationLadder:
    """Un episodio de desvío a la vez; el motor alimenta los ticks."""

    def __init__(self, cfg: AlertasCfg, on_event=None, reloj=time.time) -> None:
        self.cfg = cfg
        self.on_event = on_event or (lambda tipo, motivo: None)
        self.reloj = reloj

        self.activo = False          # hay episodio abierto
        self.silencioso = False      # tope horario alcanzado en este episodio
        self._t0: float | None = None
        self._disparadas: set[int] = set()
        self._cooldown_hasta: float | None = None
        self._ciclos_hora: deque[float] = deque()
        self._tope_emitido = False

    # ------------------------------------------------------------------ #

    def en_cooldown(self, ahora: float | None = None) -> bool:
        ahora = self.reloj() if ahora is None else ahora
        return self._cooldown_hasta is not None and ahora < self._cooldown_hasta

    def begin(self, ahora: float, niveles_cubiertos: tuple[int, ...] = ()) -> bool:
        """Abre un ciclo de escalada; False si el tope horario lo impide.

        ``niveles_cubiertos`` (v0.5.0) marca niveles que ya se entregaron por
        otro canal al abrir el episodio — en el Modo Anclado la pregunta
        contextual hace de N0/N1, así que esos dos niveles no vuelven a sonar
        veinte y treinta segundos después.
        """
        self._podar_ciclos(ahora)
        if len(self._ciclos_hora) >= self.cfg.tope_por_hora:
            self.silencioso = True
            if not self._tope_emitido:
                self._tope_emitido = True
                self.on_event("alerta", "tope_horario")
                log.info(
                    "tope de %d escaladas/hora alcanzado: silencio hasta que vuelva el foco",
                    self.cfg.tope_por_hora,
                )
            return False
        self.silencioso = False
        self.activo = True
        self._t0 = ahora
        self._disparadas = {n for n in niveles_cubiertos if 0 <= n <= 3}
        self._cooldown_hasta = None
        self._ciclos_hora.append(ahora)
        return True

    def tick(
        self,
        ahora: float,
        minutos: float,
        motivo: str = "otro",
        tarea: str = "",
    ) -> list[Alerta]:
        """Devuelve las alertas que toca disparar en este instante."""
        if not self.activo or self._t0 is None:
            return []

        if self._cooldown_hasta is not None:
            if ahora < self._cooldown_hasta:
                return []
            # cooldown terminado y el desvío sigue: nuevo ciclo si el tope lo permite
            self._cooldown_hasta = None
            if not self.begin(ahora):
                return []

        transcurrido = ahora - self._t0
        alertas: list[Alerta] = []
        umbrales = (
            (0, self.cfg.mascota_seg, Accion.MASCOTA),
            (1, self.cfg.aviso_seg, Accion.AVISO),
            (2, self.cfg.toast_seg, Accion.TOAST),
            (3, self.cfg.voz_seg, Accion.VOZ),
        )
        # v0.3.0: modo de aviso del panel. "visual" silencia los canales
        # con sonido (N1 beep y N3 voz); la mascota (N0) y el toast (N2)
        # son canales visuales y siempre pueden disparar.
        sonido = self.cfg.modo in ("visual_sonoro", "completo")
        for nivel, umbral, accion in umbrales:
            if nivel in (1, 3) and not sonido:
                continue
            if nivel in self._disparadas or transcurrido < umbral:
                continue
            alertas.append(self._construir(nivel, accion, minutos, motivo, tarea))
            self._disparadas.add(nivel)
            if nivel == 3:
                self._cooldown_hasta = ahora + self.cfg.enfriamiento_seg
        return alertas

    def end(self, ahora: float) -> ResumenEpisodio | None:
        """Cierra el episodio (retoma del foco) y devuelve su resumen."""
        if not self.activo or self._t0 is None:
            return None
        resumen = ResumenEpisodio(
            inicio=self._t0,
            fin=ahora,
            niveles_disparados=sorted(self._disparadas),
        )
        self.activo = False
        self.silencioso = False
        self._t0 = None
        self._disparadas = set()
        self._cooldown_hasta = None
        return resumen

    # ------------------------------------------------------------------ #

    def _podar_ciclos(self, ahora: float) -> None:
        while self._ciclos_hora and ahora - self._ciclos_hora[0] > 3600:
            self._ciclos_hora.popleft()

    def _construir(
        self, nivel: int, accion: Accion, minutos: float, motivo: str, tarea: str
    ) -> Alerta:
        min_txt = _minutos_txt(minutos)
        motivo_txt = MOTIVO_TEXTO.get(motivo, MOTIVO_TEXTO["otro"])
        clausula = f" Tu tarea declarada: {tarea}." if tarea.strip() else ""

        if nivel == 0:
            return Alerta(
                nivel=0,
                accion=Accion.MASCOTA,
                mensaje="(la mascota pone cara de preocupación)",
            )
        if nivel == 1:
            return Alerta(
                nivel=1,
                accion=Accion.AVISO,
                mensaje=f"¿Seguimos con la tarea? Llevas {min_txt} min en {motivo_txt}.",
            )
        if nivel == 2:
            return Alerta(
                nivel=2,
                accion=Accion.TOAST,
                titulo=f"YourFocusGuard · desvío de {min_txt} min",
                mensaje=(
                    f"Detecté {motivo_txt}.{clausula} Cuando puedas, volvemos a la tarea."
                ),
            )
        return Alerta(
            nivel=3,
            accion=Accion.VOZ,
            titulo=f"YourFocusGuard · desvío de {min_txt} min",
            mensaje=f"Detecté {motivo_txt} durante {min_txt} min. Voz de aviso activada.",
            texto_voz=(
                f"Hola, llevas {min_txt} minutos fuera de la tarea."
                f"{' ' + tarea.strip() + ' te espera.' if tarea.strip() else ' ¿Volvemos?'}"
            ),
        )
