import os
import sys

# Resolver SSL con certificados de Windows
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import json
import logging
from typing import Any
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.parse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "app"))

from router import Router
from google_calendar import Calendar
from tasks_sync import TasksSyncManager
from timer import TimerManager
from audio_engine import AudioEngine

logger = logging.getLogger(__name__)

router = Router()
calendar = Calendar()
tasks_mgr = TasksSyncManager()
timer_mgr = TimerManager()
audio_engine = AudioEngine()

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
PORT = 8765


class AssistantHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=UI_DIR, **kwargs)

    def do_GET(self):
        url_path = urllib.parse.urlparse(self.path).path

        if url_path == "/api/tasks":
            tasks = tasks_mgr.list_tasks(filter_done=False)
            self._send_json(200, tasks)
            return

        if url_path == "/api/timers":
            timers = timer_mgr.list_active_timers()
            self._send_json(200, timers)
            return

        if url_path == "/api/audio/status":
            self._send_json(200, audio_engine.get_status())
            return

        # Archivos estáticos de la UI
        if url_path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        url_path = urllib.parse.urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            payload = {}

        if url_path == "/api/chat":
            message = payload.get("message", "").strip()
            if not message:
                self._send_json(400, {"status": "error", "message": "Mensaje vacío"})
                return

            result = router.route(message)
            action = result.get("action", "charla")
            response_payload = {"action": action, "status": "ok"}

            if action == "crear_evento":
                ev = result.get("event_data", result)
                res = calendar.create_event(
                    summary=ev.get("summary", message),
                    start_time=ev.get("start_time"),
                    end_time=ev.get("end_time"),
                    description=ev.get("description", ""),
                    location=ev.get("location", ""),
                )
                response_payload["message"] = res.get("message")
                response_payload["event"] = res

            elif action == "tarea_crear":
                title = result.get("title", message)
                priority = result.get("priority", 2)
                res = tasks_mgr.add_task(title=title, priority=priority)
                response_payload["message"] = res.get("message")
                response_payload["task"] = res.get("task")

            elif action == "tarea_listar":
                tasks = tasks_mgr.list_tasks(filter_done=False)
                pendientes = [f"• {t['title']}" for t in tasks[:5]]
                res_msg = f"Tienes {len(tasks)} pendientes:\n" + "\n".join(pendientes) if tasks else "¡No tienes tareas pendientes por ahora!"
                response_payload["message"] = res_msg
                response_payload["tasks"] = tasks

            elif action == "tarea_completar":
                query = result.get("query", message)
                res = tasks_mgr.complete_task(query)
                response_payload["message"] = res.get("message")

            elif action == "crear_alarma":
                seconds = result.get("seconds", 600)
                label = result.get("label", "Recordatorio")
                res = timer_mgr.set_timer(duration_seconds=seconds, label=label)
                response_payload["message"] = res.get("message")
                response_payload["timer"] = res

            elif action == "audio_youtube":
                query = result.get("query", "lofi beats")
                res = audio_engine.search_youtube(query)
                response_payload.update(res)

            elif action == "audio_noise":
                noise_type = result.get("noise_type", "brown")
                res = audio_engine.set_noise_mode(noise_type)
                response_payload.update(res)

            elif action == "audio_stop":
                res = audio_engine.stop()
                response_payload.update(res)

            else:
                response_payload["message"] = result.get("response", "¡Aquí estoy contigo!")

            self._send_json(200, response_payload)
            return

        if url_path == "/api/tasks":
            title = payload.get("title", "").strip()
            priority = int(payload.get("priority", 2))
            res = tasks_mgr.add_task(title=title, priority=priority)
            self._send_json(200, res)
            return

        if url_path == "/api/tasks/complete":
            query = payload.get("query", "").strip()
            res = tasks_mgr.complete_task(query)
            self._send_json(200, res)
            return

        if url_path == "/api/audio/youtube":
            query = payload.get("query", "lofi beats")
            res = audio_engine.search_youtube(query)
            self._send_json(200, res)
            return

        self._send_json(404, {"status": "error", "message": "Ruta no encontrada"})

    def _send_json(self, code: int, data: Any):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Silenciar logs verbosos en consola


def start_server():
    print("\n" + "=" * 65, flush=True)
    print("🚀 PANEL DEL ASISTENTE TDAH INICIADO", flush=True)
    print(f"🔗 Interfaz disponible en: http://localhost:{PORT}", flush=True)
    print("• Google Calendar & Tasks: Sincronización dual activa", flush=True)
    print("• Vikunja Local: Conectado a http://192.168.1.20:3456", flush=True)
    print("• Audio Engine: YouTube streaming + Ruido Marrón/Blanco activo", flush=True)
    print("=" * 65 + "\n", flush=True)

    server = HTTPServer(("localhost", PORT), AssistantHTTPHandler)
    server.serve_forever()


if __name__ == "__main__":
    start_server()
