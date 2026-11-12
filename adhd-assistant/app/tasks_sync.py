import os
import sys
import json
import logging
import threading
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "app"))

from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, ".env"))

from google_calendar import Calendar, ETIQUETA_ASISTENTE

logger = logging.getLogger(__name__)

# ⚠️ SEGURIDAD: el token de Vikunja NUNCA en el código fuente.
# Se lee desde .env (VIKUNJA_TOKEN). El token antiguo expuesto en el
# repositorio (tk_5822...) DEBE ser revocado y regenerado en Vikunja.
VIKUNJA_URL = os.getenv("VIKUNJA_URL", "http://192.168.1.20:3456").rstrip("/")
VIKUNJA_TOKEN = os.getenv("VIKUNJA_TOKEN", "").strip()
VIKUNJA_PROJECT_ID = int(os.getenv("VIKUNJA_PROJECT_ID", "1"))

LOCAL_TASKS_FILE = os.path.join(BASE_DIR, "data", "tasks.json")

#: Candado de escritura: el servidor es multi-hilo (ThreadingHTTPServer)
_bloqueo_archivo = threading.Lock()


class TasksSyncManager:
    def __init__(self):
        os.makedirs(os.path.dirname(LOCAL_TASKS_FILE), exist_ok=True)
        self.calendar = Calendar()
        if not VIKUNJA_TOKEN:
            logger.warning(
                "VIKUNJA_TOKEN no configurado en .env — la sincronización "
                "con Vikunja estará desactivada (solo Google Calendar + cache local)."
            )

    # ------------------------------------------------------------------
    # Vikunja (opcional)
    # ------------------------------------------------------------------
    def _request_vikunja(self, endpoint: str, data: Optional[dict] = None, method: str = "GET") -> Optional[Any]:
        if not VIKUNJA_TOKEN:
            return None
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

    # ------------------------------------------------------------------
    # Crear
    # ------------------------------------------------------------------
    def add_task(self, title: str, priority: int = 2, due_date: Optional[str] = None) -> Dict[str, Any]:
        """Crea la tarea en Vikunja (si hay token) y en Google Calendar (si tiene fecha)."""
        # 1. Vikunja (opcional)
        vik_payload = {
            "title": title,
            "priority": priority,  # 1=Baja, 2=Normal, 3=Alta, 4=Urgente
        }
        if due_date:
            vik_payload["due_date"] = due_date

        vik_res = self._request_vikunja(f"/api/v1/projects/{VIKUNJA_PROJECT_ID}/tasks", data=vik_payload, method="PUT")
        vik_id = vik_res.get("id") if isinstance(vik_res, dict) else None

        # 2. Google Calendar (solo si la tarea tiene fecha límite real;
        #    antes creaba un evento por cada tarea y llenaba el calendario)
        gcal_id = None
        if due_date:
            try:
                prio_label = "🔥 Alta" if priority >= 3 else "📌 Normal"
                gcal_res = self.calendar.create_event(
                    summary=f"[{prio_label}] {title}",
                    start_time=due_date,
                    description=f"{ETIQUETA_ASISTENTE} Tarea pendiente sincronizada (Vikunja ID: {vik_id})",
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

        if vik_id and gcal_id:
            mensaje = f"Tarea '{title}' guardada en Google Calendar y Vikunja."
        elif vik_id:
            mensaje = f"Tarea '{title}' guardada en Vikunja."
        elif gcal_id:
            mensaje = f"Tarea '{title}' guardada en Google Calendar."
        else:
            mensaje = f"Tarea '{title}' guardada localmente (Vikunja/Google no disponibles)."

        return {
            "status": "ok",
            "message": mensaje,
            "task": task_record,
        }

    # ------------------------------------------------------------------
    # Listar
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Completar (v0.10: ahora también limpia el evento en Google Calendar)
    # ------------------------------------------------------------------
    def complete_task(self, query: str) -> Dict[str, Any]:
        """Marca una tarea como completada por coincidencia de nombre o id.

        v0.10: si la tarea tenía un evento vinculado en Google Calendar
        (gcal_id), el evento se elimina para liberar la agenda.
        """
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
        self._request_vikunja(f"/api/v1/tasks/{vik_id}", data={"done": True}, method="POST")

        # v0.10: eliminar el evento vinculado en Google Calendar (si existe)
        gcal_borrado = False
        registro_local = self._buscar_registro_local(vik_id, target["title"])
        gcal_id = (registro_local or {}).get("gcal_id") or target.get("gcal_id")
        if gcal_id:
            res_del = self.calendar.eliminar_evento(gcal_id)
            gcal_borrado = res_del.get("status") == "ok"

        # Actualizar también el cache local para que el fallback quede consistente
        self._mark_local_done(vik_id, target["title"])

        mensaje = f"¡Excelente! Marqué como completada: '{target['title']}'."
        if gcal_borrado:
            mensaje += " También liberé el hueco en tu Google Calendar."

        return {
            "status": "ok",
            "message": mensaje,
            "completed_task": target,
            "gcal_eliminado": gcal_borrado,
        }

    # ------------------------------------------------------------------
    # SINCRONIZACIÓN BIDIRECCIONAL (nuevo en v0.10)
    # ------------------------------------------------------------------
    def sincronizar_calendario(self) -> Dict[str, Any]:
        """Reconcilia tareas locales (cache) con Google Calendar, en ambos sentidos.

        - Tarea con fecha y SIN evento en Calendar -> crea el evento (catch-up,
          p.ej. tareas creadas sin conexión).
        - Tarea con evento VINCULADO que fue MOVIDO en Google -> actualiza la
          fecha local de la tarea.
        - Tarea con evento vinculado que fue BORRADO en Google -> desvincula
          (la tarea se queda, se reporta como huérfana).

        Devuelve un reporte {creados, actualizados, huerfanos, errores}.
        """
        reporte = {"creados": [], "actualizados": [], "huerfanos": [], "errores": []}
        tareas = self._read_local_tasks(filter_done=False)

        for t in tareas:
            due = t.get("due_date")
            if not due:
                continue  # sin fecha: nada que sincronizar con el calendario

            gcal_id = t.get("gcal_id")

            # 1) Sin evento vinculado -> crearlo
            if not gcal_id:
                if not self.calendar.is_authenticated():
                    continue
                try:
                    prio_label = "🔥 Alta" if t.get("priority", 2) >= 3 else "📌 Normal"
                    res = self.calendar.create_event(
                        summary=f"[{prio_label}] {t['title']}",
                        start_time=due,
                        description=f"{ETIQUETA_ASISTENTE} Tarea pendiente (catch-up sync)",
                    )
                    if res.get("status") == "ok":
                        t["gcal_id"] = res.get("id")
                        reporte["creados"].append(t["title"])
                    else:
                        reporte["errores"].append(f"{t['title']}: {res.get('message')}")
                except Exception as e:
                    reporte["errores"].append(f"{t['title']}: {e}")
                continue

            # 2) Con evento vinculado -> verificar que siga vivo y en la misma fecha
            ev = self.calendar.obtener_evento(gcal_id)
            if ev is None:
                # Borrado/cancelado en Google -> desvincular (huérfana)
                t["gcal_id"] = None
                t["huerfana_desde"] = datetime.now().isoformat()
                reporte["huerfanos"].append(t["title"])
                continue

            ev_inicio = (ev.get("start") or "")[: len(due)]
            if ev_inicio and ev_inicio != due:
                # Fue movido en Google -> la fecha nueva gana
                t["due_date"] = ev.get("start")
                reporte["actualizados"].append(t["title"])

        # Persistir cambios locales bajo candado
        try:
            with _bloqueo_archivo:
                with open(LOCAL_TASKS_FILE, "w", encoding="utf-8") as f:
                    json.dump(tareas, f, indent=2, ensure_ascii=False)
        except Exception as e:
            reporte["errores"].append(f"No se pudo guardar el cache local: {e}")

        return {
            "status": "ok",
            "message": (
                f"Sincronización lista: {len(reporte['creados'])} eventos creados, "
                f"{len(reporte['actualizados'])} tareas actualizadas, "
                f"{len(reporte['huerfanos'])} huérfanas."
                + (f" Errores: {len(reporte['errores'])}." if reporte["errores"] else "")
            ),
            "reporte": reporte,
        }

    # ------------------------------------------------------------------
    # Cache local
    # ------------------------------------------------------------------
    def _buscar_registro_local(self, task_id, title: str) -> Optional[dict]:
        """Busca el registro completo en el cache local (trae gcal_id, etc.)."""
        for t in self._read_local_tasks(False):
            coincide_id = (
                task_id is not None
                and (t.get("id") == task_id or t.get("vikunja_id") == task_id)
            )
            coincide_titulo = title is not None and t.get("title") == title
            if coincide_id or coincide_titulo:
                return t
        return None

    def _mark_local_done(self, task_id, title: str):
        """Marca como hecha la tarea en el cache local (por id, vikunja_id o título)."""
        try:
            with _bloqueo_archivo:
                tasks = self._read_local_tasks(False)
                for t in tasks:
                    coincide_id = (
                        task_id is not None
                        and (t.get("id") == task_id or t.get("vikunja_id") == task_id)
                    )
                    coincide_titulo = title is not None and t.get("title") == title
                    if coincide_id or coincide_titulo:
                        t["done"] = True
                        break
                with open(LOCAL_TASKS_FILE, "w", encoding="utf-8") as f:
                    json.dump(tasks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Error actualizando cache local: {e}")

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
        try:
            with _bloqueo_archivo:
                tasks = self._read_local_tasks(False)
                tasks.append(task)
                with open(LOCAL_TASKS_FILE, "w", encoding="utf-8") as f:
                    json.dump(tasks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Error escribiendo cache local de tareas: {e}")
