import os
import sys
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "app"))

from google_calendar import Calendar

logger = logging.getLogger(__name__)

VIKUNJA_URL = "http://192.168.1.20:3456"
VIKUNJA_TOKEN = "tk_582247f511958f68885e45a26072b5caa07173b5"
VIKUNJA_PROJECT_ID = 1

LOCAL_TASKS_FILE = os.path.join(BASE_DIR, "data", "tasks.json")


class TasksSyncManager:
    def __init__(self):
        os.makedirs(os.path.dirname(LOCAL_TASKS_FILE), exist_ok=True)
        self.calendar = Calendar()

    def _request_vikunja(self, endpoint: str, data: Optional[dict] = None, method: str = "GET") -> Optional[Any]:
        url = f"{VIKUNJA_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {VIKUNJA_TOKEN}",
            "Content-Type": "application/json",
        }
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"Error conectando con Vikunja ({endpoint}): {e}")
            return None

    def add_task(self, title: str, priority: int = 2, due_date: Optional[str] = None) -> Dict[str, Any]:
        """Crea la tarea tanto en Vikunja como en Google Calendar."""
        # 1. Vikunja
        vik_payload = {
            "title": title,
            "priority": priority,  # 1=Baja, 2=Normal, 3=Alta, 4=Urgente
        }
        if due_date:
            vik_payload["due_date"] = due_date

        vik_res = self._request_vikunja(f"/api/v1/projects/{VIKUNJA_PROJECT_ID}/tasks", data=vik_payload, method="PUT")
        vik_id = vik_res.get("id") if isinstance(vik_res, dict) else None

        # 2. Google Calendar (como evento/tarea con prefijo de foco)
        gcal_id = None
        now_iso = due_date or datetime.now().strftime("%Y-%m-%dT10:00:00-05:00")
        try:
            prio_label = "🔥 Alta" if priority >= 3 else "📌 Normal"
            gcal_res = self.calendar.create_event(
                summary=f"[{prio_label}] {title}",
                start_time=now_iso,
                description=f"Tarea pendiente sincronizada con Vikunja (ID: {vik_id})",
            )
            gcal_id = gcal_res.get("id")
        except Exception as e:
            logger.warning(f"No se pudo sincronizar tarea en Google Calendar: {e}")

        # Guardar en local cache
        task_record = {
            "id": vik_id or int(datetime.now().timestamp()),
            "title": title,
            "priority": priority,
            "due_date": due_date,
            "done": False,
            "vikunja_id": vik_id,
            "gcal_id": gcal_id,
            "created_at": datetime.now().isoformat(),
        }
        self._append_local_task(task_record)

        return {
            "status": "ok",
            "message": f"Tarea '{title}' guardada en Google Calendar y Vikunja.",
            "task": task_record,
        }

    def list_tasks(self, filter_done: bool = False) -> List[Dict[str, Any]]:
        """Obtiene las tareas priorizando Vikunja y ordenadas por prioridad (urgentes primero)."""
        vik_tasks = self._request_vikunja(f"/api/v1/projects/{VIKUNJA_PROJECT_ID}/tasks")
        if isinstance(vik_tasks, list):
            tasks = []
            for t in vik_tasks:
                is_done = t.get("done", False)
                if not filter_done or not is_done:
                    tasks.append({
                        "id": t.get("id"),
                        "title": t.get("title"),
                        "done": is_done,
                        "priority": t.get("priority", 2),
                        "due_date": t.get("due_date"),
                    })
            # Ordenar por prioridad descendente (4=urgente, 1=baja)
            tasks.sort(key=lambda x: (not x["done"], x["priority"]), reverse=True)
            return tasks

        # Fallback a local
        return self._read_local_tasks(filter_done)

    def complete_task(self, query: str) -> Dict[str, Any]:
        """Marca una tarea como completada por coincidencia de nombre o id."""
        tasks = self.list_tasks(filter_done=False)
        target = None

        query_clean = query.lower().strip()
        for t in tasks:
            if query_clean in t["title"].lower() or str(t["id"]) == query_clean:
                target = t
                break

        if not target:
            return {"status": "not_found", "message": f"No encontré una tarea pendiente que coincida con '{query}'."}

        # Actualizar en Vikunja
        vik_id = target["id"]
        res = self._request_vikunja(f"/api/v1/tasks/{vik_id}", data={"done": True}, method="POST")

        return {
            "status": "ok",
            "message": f"¡Excelente! Marqué como completada: '{target['title']}'.",
            "completed_task": target,
        }

    def _read_local_tasks(self, filter_done: bool) -> List[Dict[str, Any]]:
        if not os.path.exists(LOCAL_TASKS_FILE):
            return []
        try:
            with open(LOCAL_TASKS_FILE, "r", encoding="utf-8") as f:
                tasks = json.load(f)
            if filter_done:
                return [t for t in tasks if not t.get("done")]
            return tasks
        except Exception:
            return []

    def _append_local_task(self, task: dict):
        tasks = self._read_local_tasks(False)
        tasks.append(task)
        try:
            with open(LOCAL_TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Error escribiendo cache local de tareas: {e}")
