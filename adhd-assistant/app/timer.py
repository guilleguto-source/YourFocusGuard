import os
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

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
            "message": f"Alarma programada en {' '.join(tiempo_texto)} ({target_time.strftime('%H:%M:%S')}): '{label}'",
            "target_time": target_time.strftime("%H:%M:%S"),
        }

    def _run_timer(self, duration: float, label: str, record: dict):
        time.sleep(duration)
        record["status"] = "finished"
        print(f"\n" + "🔔" * 20, flush=True)
        print(f"⏰ ¡ALARMA / RECORDATORIO!: {label}", flush=True)
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
