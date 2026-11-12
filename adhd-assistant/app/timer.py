import os
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from utilidades import formatear_fecha_hora_es, formatear_hora_es

logger = logging.getLogger(__name__)

active_timers: List[Dict[str, Any]] = []


class TimerManager:
    def __init__(self):
        pass

    def set_timer(self, duration_seconds: float, label: str) -> Dict[str, Any]:
        """Programa un temporizador/alarma en segundo plano."""
        target_time = datetime.now() + timedelta(seconds=duration_seconds)
        timer_id = int(time.time() * 1000)

        record = {
            "id": timer_id,
            "label": label,
            "duration": duration_seconds,
            "target_time": target_time.strftime("%H:%M:%S"),
            # v0.10: fecha completa (antes solo HH:MM:SS y las alarmas de +24 h
            # se veían raras, p.ej. 'alarma a las 03:10' sin decir qué día)
            "target_fecha": formatear_fecha_hora_es(target_time),
            "target_iso": target_time.isoformat(),
            "status": "active",
        }
        active_timers.append(record)

        thread = threading.Thread(
            target=self._run_timer,
            args=(duration_seconds, label, record),
            daemon=True,
        )
        thread.start()

        horas = int(duration_seconds // 3600)
        minutos = int((duration_seconds % 3600) // 60)
        segundos = int(duration_seconds % 60)
        tiempo_texto = []
        if horas > 0:
            tiempo_texto.append(f"{horas}h")
        if minutos > 0:
            tiempo_texto.append(f"{minutos}m")
        if segundos > 0 or not tiempo_texto:
            tiempo_texto.append(f"{segundos}s")

        return {
            "status": "ok",
            "message": (
                f"Alarma programada en {' '.join(tiempo_texto)} "
                f"({formatear_fecha_hora_es(target_time)}): '{label}'"
            ),
            "target_time": target_time.strftime("%H:%M:%S"),
            "target_fecha": record["target_fecha"],
        }

    def _run_timer(self, duration: float, label: str, record: dict):
        time.sleep(duration)
        # Marcar terminado ANTES de la señal para que la UI lo detecte
        record["status"] = "finished"
        record["announced"] = False
        # v0.10: momento exacto de vencimiento con fecha completa
        vencimiento = datetime.now()
        record["finished_fecha"] = formatear_fecha_hora_es(vencimiento)
        record["mensaje_hablado"] = (
            f"¡Se acabó el tiempo! {label}. "
            f"Son las {formatear_hora_es(vencimiento)} del {formatear_fecha_hora_es(vencimiento).split(', ')[0]}."
        )

        print(f"\n" + "🔔" * 20, flush=True)
        print(f"⏰ ¡ALARMA / RECORDATORIO!: {label}", flush=True)
        print(f"   📅 {record['finished_fecha']}", flush=True)
        print("🔔" * 20 + "\n", flush=True)

        # Sonar beep o audio si está disponible
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 300)
                time.sleep(0.1)
        except Exception:
            pass

    def list_active_timers(self) -> List[Dict[str, Any]]:
        return [t for t in active_timers if t["status"] == "active"]

    def pop_finished_unannounced(self) -> List[Dict[str, Any]]:
        """Devuelve las alarmas vencidas aún no anunciadas y las marca.

        La UI hace polling a /api/timers/announce cada pocos segundos; al
        recibir una alarma la reproduce con voz neuronal y beep en el
        navegador (visible aunque la consola esté cerrada).
        """
        pendientes = []
        for t in active_timers:
            if t["status"] == "finished" and not t.get("announced"):
                t["announced"] = True
                pendientes.append(dict(t))
        # Limpieza: mantener la lista acotada (máx. 20 registros viejos)
        if len(active_timers) > 20:
            del active_timers[: len(active_timers) - 20]
        return pendientes
