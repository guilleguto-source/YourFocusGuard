import os
import glob
import json
import time
import sqlite3
import datetime
from typing import Dict, Any, List

ANTIGRAVITY_DIR = os.path.expanduser(r"~\.gemini\antigravity")
DEEPSEEK_DIR = r"C:\Users\Guill\Documents\deepseek-harness"

_LAST_STATE = {
    "has_pending_plan": False,
    "last_working_id": None,
    "last_notif_time": 0,
}


def _extraer_resumen_amigable() -> str:
    """Extrae un resumen comprensible y no técnico del plan activo."""
    plan_path = os.path.join(
        r"C:\Users\Guill\Documents\antigravity\blissful-einstein", ".agents", "plans", "active-plan.md"
    )
    if os.path.isfile(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                title = ""
                detalles = []
                for line in lines:
                    line_s = line.strip()
                    if line_s.startswith("# Plan:"):
                        title = line_s.replace("# Plan:", "").strip()
                    elif line_s.startswith("- ") or line_s.startswith("* "):
                        limpio = line_s.lstrip("-* ").strip()
                        if len(limpio) > 8 and not limpio.startswith("["):
                            detalles.append(limpio)
                if title:
                    det = detalles[0] if detalles else "Mejoras y cambios listos para aplicar"
                    return f"{title}. {det}"
        except Exception:
            pass
    return "Plan preparado con ajustes y optimizaciones listos para tu confirmación."


def _notificar_phonebox(titulo: str, mensaje: str, cambiar_pantalla: str = None):
    try:
        import urllib.request
        if cambiar_pantalla:
            req_goto = urllib.request.Request(
                f"http://127.0.0.1:8765/api/goto/{cambiar_pantalla}",
                data=b"{}",
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req_goto, timeout=2)

        payload = json.dumps({
            "title": titulo,
            "message": mensaje,
            "vibrate": True,
        }).encode("utf-8")
        req_notif = urllib.request.Request(
            "http://127.0.0.1:8765/api/notify",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req_notif, timeout=2)
    except Exception:
        pass


def _tiempo_relativo(iso_str: str) -> str:
    try:
        # Formato ISO tipo '2026-11-17 04:06:38.9296612+00:00'
        limpio = iso_str.split("+")[0].strip()
        dt = datetime.datetime.fromisoformat(limpio)
        ahora = datetime.datetime.utcnow()
        diff = (ahora - dt).total_seconds()
        if diff < 60:
            return f"{int(diff)}s"
        elif diff < 3600:
            return f"{int(diff // 60)}m"
        elif diff < 86400:
            return f"{int(diff // 3600)}h {int((diff % 3600) // 60)}m"
        else:
            return f"{int(diff // 86400)}d"
    except Exception:
        return "–"


def get_antigravity_state() -> Dict[str, Any]:
    db_path = os.path.join(ANTIGRAVITY_DIR, "conversation_summaries.db")
    conversaciones: List[Dict[str, Any]] = []
    activa = None

    # 1. Sesiones desde base de datos SQLite
    if os.path.isfile(db_path):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            c = conn.cursor()
            c.execute(
                """
                SELECT conversation_id, title, status, step_count, last_modified_time, not_fully_idle
                FROM conversation_summaries
                ORDER BY last_modified_time DESC
                LIMIT 8
                """
            )
            for row in c.fetchall():
                c_id, title, status, steps, last_mod, not_idle = row
                estado_ui = "working" if not_idle or "RUNNING" in str(status) else "idle"
                titulo_ui = title.strip() if title and title.strip() else f"Sesión {c_id[:8]}"
                tiempo_ui = _tiempo_relativo(last_mod)

                item = {
                    "id": c_id,
                    "title": titulo_ui,
                    "status": estado_ui,
                    "steps": steps or 0,
                    "updated": tiempo_ui,
                    "last_modified": last_mod,
                }
                conversaciones.append(item)
                if activa is None:
                    activa = item
            conn.close()
        except Exception as e:
            pass

    # 2. Información del turno en vivo de la conversación activa
    turno_info = {
        "step_index": activa["steps"] if activa else 0,
        "current_tool": "En reposo",
        "action_detail": "Esperando instrucciones",
        "has_pending_plan": False,
        "subagents_active": 0,
    }

    if activa:
        t_path = os.path.join(
            ANTIGRAVITY_DIR, "brain", activa["id"], ".system_generated", "logs", "transcript.jsonl"
        )
        if os.path.isfile(t_path):
            try:
                with open(t_path, "r", encoding="utf-8") as f:
                    lineas = f.readlines()
                    if lineas:
                        ultimo = json.loads(lineas[-1])
                        turno_info["step_index"] = ultimo.get("step_index", activa["steps"])
                        t_calls = ultimo.get("tool_calls") or []
                        if t_calls:
                            herramienta = t_calls[-1].get("toolName", "Herramienta")
                            turno_info["current_tool"] = herramienta
                            turno_info["action_detail"] = f"Ejecutando {herramienta}"
                        elif ultimo.get("type") == "USER_INPUT":
                            turno_info["current_tool"] = "Procesando"
                            turno_info["action_detail"] = "Analizando petición del usuario"
                        else:
                            turno_info["current_tool"] = "Completado"
                            turno_info["action_detail"] = "Turno finalizado"

                        # Detectar plan pendiente
                        for lin in reversed(lineas[-5:]):
                            obj = json.loads(lin)
                            for call in obj.get("tool_calls") or []:
                                if call.get("arguments", {}).get("ArtifactMetadata", {}).get("RequestFeedback"):
                                    turno_info["has_pending_plan"] = True
                                    break
            except Exception:
                pass

        if turno_info["has_pending_plan"]:
            turno_info["plan_summary"] = _extraer_resumen_amigable()
            if not _LAST_STATE["has_pending_plan"]:
                _LAST_STATE["has_pending_plan"] = True
                _notificar_phonebox("📋 Plan listo para aprobación", turno_info["plan_summary"], cambiar_pantalla="work")
        else:
            _LAST_STATE["has_pending_plan"] = False

        # Detección de finalización de tarea
        prev_id = _LAST_STATE.get("last_working_id")
        if activa["status"] == "working":
            _LAST_STATE["last_working_id"] = activa["id"]
        elif activa["status"] == "idle" and prev_id == activa["id"]:
            _LAST_STATE["last_working_id"] = None
            if time.time() - _LAST_STATE.get("last_notif_time", 0) > 15:
                _LAST_STATE["last_notif_time"] = time.time()
                _notificar_phonebox("✅ Tarea finalizada", f"{activa['title']}: Turno completado.")

    # 3. Estado de proceso del Language Server
    ls_info = {"running": False, "pid": None, "memory_mb": 0}
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            if "language_server" in p.info["name"].lower():
                ls_info["running"] = True
                ls_info["pid"] = p.info["pid"]
                ls_info["memory_mb"] = round(p.info["memory_info"].rss / (1024 * 1024), 1)
                break
    except Exception:
        pass

    return {
        "engine": "Antigravity 2.0",
        "status": "online" if ls_info["running"] else "idle",
        "language_server": ls_info,
        "sessions": conversaciones,
        "active_session": activa,
        "live_step": turno_info,
    }


def get_deepseek_state() -> Dict[str, Any]:
    workspaces = []
    dossiers = []

    if os.path.isdir(DEEPSEEK_DIR):
        try:
            for item in os.listdir(DEEPSEEK_DIR):
                full = os.path.join(DEEPSEEK_DIR, item)
                if os.path.isdir(full):
                    workspaces.append(item)
                    for doc in os.listdir(full):
                        if doc.endswith((".md", ".json", ".py")):
                            d_path = os.path.join(full, doc)
                            mtime = os.path.getmtime(d_path)
                            dossiers.append({
                                "name": doc,
                                "workspace": item,
                                "updated": _tiempo_relativo(
                                    datetime.datetime.utcfromtimestamp(mtime).isoformat()
                                ),
                            })
        except Exception:
            pass

    # Verificar si hay procesos de deepseek
    running = False
    pid = None
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if "deepseek" in cmd or "deepseek" in p.info.get("name", "").lower():
                running = True
                pid = p.info["pid"]
                break
    except Exception:
        pass

    return {
        "engine": "DeepSeek Harness",
        "status": "online" if running else ("ready" if workspaces else "inactive"),
        "pid": pid,
        "workspaces": workspaces,
        "dossiers": dossiers,
        "active_workspace": workspaces[0] if workspaces else "default-workspace",
    }


def get_all_state() -> Dict[str, Any]:
    return {
        "status": "ok",
        "ts": time.time(),
        "antigravity": get_antigravity_state(),
        "deepseek": get_deepseek_state(),
    }
