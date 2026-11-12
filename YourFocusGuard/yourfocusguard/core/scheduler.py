"""Programador de recordatorios y rutinas de hábitos TDAH (v0.8.3 Fase 3).

Permite programar avisos temporales por lenguaje natural por voz
("recuérdame en 30 minutos preparar la comida") y vigilar rutinas
periódicas (pausas activas, hora de ejercicio) sin bloquear el hilo principal.
"""
from __future__ import annotations

import datetime
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yourfocusguard.config import Config

log = logging.getLogger(__name__)


@dataclass
class Recordatorio:
    id: str
    mensaje: str
    timestamp_disparo: float
    disparado: bool = False


def extraer_recordatorio_voz(texto: str) -> tuple[bool, str, float]:
    """Extrae la intención de recordatorio, el motivo y el delta en minutos.

    Ejemplos soportados:
      - "recuérdame en 30 minutos preparar la comida" -> (True, "Preparar la comida", 30.0)
      - "recuerda en media hora llamar al cliente"     -> (True, "Llamar al cliente", 30.0)
      - "recuerdame en 1 hora salir al banco"         -> (True, "Salir al banco", 60.0)
      - "avísame en 15 min tomar agua"                -> (True, "Tomar agua", 15.0)

    Returns:
        (es_recordatorio, mensaje_tarea, delta_minutos)
    """
    t = (texto or "").strip()
    if not t:
        return False, "", 0.0

    t_baja = t.lower()
    # Buscar patrones de tiempo
    # Caso especial: media hora
    patron_media_hora = re.search(
        r"(?:recu[eé]rdame|recuerda|av[ií]same)\s+en\s+media\s+hora(?:\s+(?:de|para|que)?\s*(.*))?",
        t_baja,
    )
    if patron_media_hora:
        resto = (patron_media_hora.group(1) or "Recordatorio").strip()
        resto = re.sub(r"^(?:de|para|a|que)\s+", "", resto).strip()
        tarea = resto[0].upper() + resto[1:] if resto else "Recordatorio programado"
        return True, tarea, 30.0

    # Caso general: en X minutos / horas
    patron_num = re.search(
        r"(?:recu[eé]rdame|recuerda|av[ií]same|alarma)\s+en\s+(\d+(?:[.,]\d+)?)\s*(minutos?|mins?|m|horas?|h|segundos?|s)?(?:\s+(.*))?",
        t_baja,
    )
    if patron_num:
        val_str = patron_num.group(1).replace(",", ".")
        try:
            val = float(val_str)
        except ValueError:
            return False, "", 0.0

        unidad = (patron_num.group(2) or "minutos").lower()
        if unidad.startswith("h"):
            minutos = val * 60.0
        elif unidad.startswith("s"):
            minutos = max(0.1, val / 60.0)
        else:
            minutos = val

        resto = (patron_num.group(3) or "").strip()
        resto = re.sub(r"^(?:de|para|a|que)\s+", "", resto).strip()
        tarea = resto[0].upper() + resto[1:] if resto else "Recordatorio"
        return True, tarea, minutos

    return False, "", 0.0


class Scheduler:
    """Motor en memoria para temporizadores, recordatorios y rutinas."""

    def __init__(self, cfg: "Config | None" = None) -> None:
        self.cfg = cfg
        self._recordatorios: list[Recordatorio] = []
        self._candado = threading.Lock()
        self._contador = 0
        self._ultimo_check_rutina = time.time()
        self._ultimo_dia_ejercicio = ""

    def programar(self, mensaje: str, delta_minutos: float) -> Recordatorio:
        """Registra un recordatorio a disparar en delta_minutos."""
        with self._candado:
            self._contador += 1
            rec_id = f"rec_{self._contador}_{int(time.time())}"
            ts = time.time() + (delta_minutos * 60.0)
            rec = Recordatorio(id=rec_id, mensaje=mensaje, timestamp_disparo=ts)
            self._recordatorios.append(rec)
            log.info("Recordatorio '%s' programado para dentro de %.1f min", mensaje, delta_minutos)
            return rec

    def verificar_pendientes(self) -> list[str]:
        """Comprueba y consume avisos que hayan cumplido su plazo."""
        ahora = time.time()
        avisos: list[str] = []

        # 1. Recordatorios puntuales
        with self._candado:
            for r in self._recordatorios:
                if not r.disparado and ahora >= r.timestamp_disparo:
                    r.disparado = True
                    avisos.append(f"⏰ Recordatorio: {r.mensaje}")

            # Limpiar disparados antiguos
            self._recordatorios = [r for r in self._recordatorios if not r.disparado]

        # 2. Rutinas periódicas (si están habilitadas en config)
        rutinas = getattr(self.cfg, "rutinas", None)
        if rutinas and getattr(rutinas, "habilitado", True):
            # Pausa activa por intervalo
            intervalo_min = getattr(rutinas, "pausa_activa_cada_min", 0)
            if intervalo_min > 0:
                if ahora - self._ultimo_check_rutina >= (intervalo_min * 60.0):
                    self._ultimo_check_rutina = ahora
                    msg = getattr(rutinas, "pausa_activa_mensaje", "Toca pausa activa y agua.")
                    avisos.append(f"🧘 {msg}")

            # Ejercicio a hora fija diaria
            hora_fija = (getattr(rutinas, "ejercicio_hora", "") or "").strip()
            if hora_fija:
                ahora_dt = datetime.datetime.now()
                dia_actual = ahora_dt.strftime("%Y-%m-%d")
                hora_actual = ahora_dt.strftime("%H:%M")
                if hora_actual == hora_fija and self._ultimo_dia_ejercicio != dia_actual:
                    self._ultimo_dia_ejercicio = dia_actual
                    msg = getattr(rutinas, "ejercicio_mensaje", "Hora de hacer ejercicio.")
                    avisos.append(f"🏃 {msg}")

        return avisos


_SCHEDULER_GLOBAL: Scheduler | None = None
_SCHEDULER_LOCK = threading.Lock()


def obtener_scheduler(cfg: "Config | None" = None) -> Scheduler:
    """Retorna la instancia global del programador."""
    global _SCHEDULER_GLOBAL
    with _SCHEDULER_LOCK:
        if _SCHEDULER_GLOBAL is None:
            _SCHEDULER_GLOBAL = Scheduler(cfg)
        elif cfg is not None:
            _SCHEDULER_GLOBAL.cfg = cfg
        return _SCHEDULER_GLOBAL
