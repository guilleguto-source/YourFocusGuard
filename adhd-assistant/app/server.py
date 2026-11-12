import os
import sys
import time

# Resolver SSL con certificados de Windows
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import json
import logging
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import urllib.parse
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "app"))

from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, ".env"))

from router import Router
from google_calendar import Calendar
from tasks_sync import TasksSyncManager
from timer import TimerManager
from audio_engine import AudioEngine
import tts
import memoria
import herramientas

logger = logging.getLogger(__name__)

router = Router()
calendar = Calendar()
tasks_mgr = TasksSyncManager()
timer_mgr = TimerManager()
audio_engine = AudioEngine()

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

#: Puerto configurable (lo usa pruebas_automaticas.py para no chocar con
#: tu servidor real en 8765)
PORT = int(os.getenv("ASISTENTE_PUERTO", "8765"))

#: Orígenes permitidos para la API local (la UI se sirve desde el mismo
#: servidor). Antes respondía Access-Control-Allow-Origin: * , lo que
#: permitía que CUALQUIER web abierta en el navegador leyera tus tareas
#: o enviara órdenes a http://localhost:8765.
ORIGENES_PERMITIDOS = {
    f"http://localhost:{PORT}",
    f"http://127.0.0.1:{PORT}",
}

_INICIO = time.time()


def _version() -> str:
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as f:
            return json.load(f).get("version", "?")
    except Exception:
        return "?"


class AssistantHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=UI_DIR, **kwargs)

    # ---------- Seguridad de origen ----------
    def _origen_permitido(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True  # misma origen (navegador no envía Origin en GET propio) o curl
        return origin in ORIGENES_PERMITIDOS

    def _rechazar_origen(self):
        self.send_response(403)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"status": "error", "message": "Origin no autorizado"}')

    # ---------- GET ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        url_path = parsed.path

        # Rutas de API: verificar origen antes de responder
        if url_path.startswith("/api/"):
            if not self._origen_permitido():
                self._rechazar_origen()
                return

            if url_path == "/api/tasks":
                tasks = tasks_mgr.list_tasks(filter_done=False)
                self._send_json(200, tasks)
                return

            if url_path == "/api/timers":
                self._send_json(200, timer_mgr.list_active_timers())
                return

            if url_path == "/api/timers/announce":
                # Devuelve (y marca) alarmas vencidas sin anunciar para que
                # la UI las reproduzca con voz y beep aunque la consola esté cerrada
                self._send_json(200, timer_mgr.pop_finished_unannounced())
                return

            if url_path == "/api/audio/status":
                self._send_json(200, audio_engine.get_status())
                return

            if url_path == "/api/tts/voices":
                self._send_json(200, {
                    "perfil_activo": tts.perfil_actual(),
                    "perfiles": tts.listar_perfiles(),
                })
                return

            if url_path == "/api/tts":
                params = urllib.parse.parse_qs(parsed.query)
                texto = (params.get("text", [""])[0] or "").strip()[:1000]
                perfil = params.get("perfil", [None])[0]
                if not texto:
                    self._send_json(400, {"status": "error", "message": "Falta el parámetro 'text'"})
                    return

                ruta_mp3 = tts.sintetizar(texto, perfil)
                if ruta_mp3 is None:
                    # Sin edge-tts o sin internet: la UI usará la voz del navegador
                    self._send_json(503, {"status": "error", "message": "TTS neuronal no disponible"})
                    return

                try:
                    with open(ruta_mp3, "rb") as f:
                        audio_bytes = f.read()
                except Exception as e:
                    logger.warning("Error leyendo MP3 de caché: %s", e)
                    self._send_json(503, {"status": "error", "message": "TTS no disponible"})
                    return

                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio_bytes)))
                self.end_headers()
                self.wfile.write(audio_bytes)
                return

            # ---- v0.11: memoria ----
            if url_path == "/api/notas":
                params = urllib.parse.parse_qs(parsed.query)
                consulta = (params.get("q", [""])[0] or "").strip()
                if consulta:
                    self._send_json(200, {"status": "ok", "query": consulta, "notas": memoria.buscar_notas(consulta)})
                else:
                    self._send_json(200, {"status": "ok", "notas": memoria.listar_notas()})
                return

            if url_path == "/api/briefing":
                self._send_json(200, memoria.briefing_diario(calendar, tasks_mgr))
                return

            # ---- v0.12: preparación MCP ----
            if url_path == "/api/herramientas":
                self._send_json(200, {
                    "status": "ok",
                    "version": _version(),
                    "herramientas": herramientas.esquemas_mcp(),
                })
                return

            if url_path == "/api/salud":
                self._send_json(200, self._estado_salud())
                return

            # ---- v0.10: calendario ----
            if url_path == "/api/calendario/eventos":
                dias = 1
                try:
                    params = urllib.parse.parse_qs(parsed.query)
                    dias = int(params.get("dias", ["1"])[0])
                except Exception:
                    pass
                self._send_json(200, {"status": "ok", "eventos": calendar.listar_eventos(dias=dias)})
                return

            self._send_json(404, {"status": "error", "message": "Ruta no encontrada"})
            return

        # Archivos estáticos de la UI
        if url_path == "/":
            self.path = "/index.html"
        return super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        url_path = urllib.parse.urlparse(self.path).path

        if url_path.startswith("/api/"):
            if not self._origen_permitido():
                self._rechazar_origen()
                return

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
                summary = result.get("summary", message)
                start_time = result.get("start_time")
                end_time = result.get("end_time")

                dt_inicio = None
                if start_time:
                    try:
                        from datetime import datetime, timedelta
                        dt_inicio = datetime.fromisoformat(start_time)
                    except Exception:
                        dt_inicio = None

                fecha_txt = utilidades.formatear_fecha_hora_es(dt_inicio) if dt_inicio else (start_time or "próximamente")
                if dt_inicio and not end_time:
                    dt_fin = dt_inicio + timedelta(hours=1)
                    end_time = dt_fin.isoformat()
                    hora_fin = utilidades.formatear_hora_es(dt_fin)
                    msg_propuesta = f"¿Agendo '{summary}' para el {fecha_txt} (hasta las {hora_fin})?"
                else:
                    msg_propuesta = f"¿Agendo '{summary}' para el {fecha_txt}?"

                response_payload["action"] = "confirmar_evento"
                response_payload["message"] = msg_propuesta
                response_payload["propuesta"] = {
                    "summary": summary,
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": result.get("description", ""),
                    "location": result.get("location", ""),
                }
                response_payload["auto_confirmar_seg"] = 15
                response_payload["opciones"] = ["Agendar", "Cancelar"]

            elif action == "tarea_crear":
                res = tasks_mgr.add_task(
                    title=result.get("title", message),
                    priority=result.get("priority", 2),
                    due_date=result.get("due_date"),
                )
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

            elif action == "nota_crear":  # v0.11
                res = memoria.crear_nota(result.get("texto", message), fuente="voz")
                response_payload["message"] = res.get("message", "Nota guardada.")
                response_payload["nota"] = res.get("nota")

            elif action == "nota_buscar":  # v0.11
                encontradas = memoria.buscar_notas(result.get("query", message))
                if encontradas:
                    lista = "\n".join(f"• {n['texto']}" for n in encontradas[:5])
                    response_payload["message"] = f"Encontré {len(encontradas)} nota(s):\n{lista}"
                else:
                    response_payload["message"] = "No encontré notas con eso. Prueba con otras palabras."
                response_payload["notas"] = encontradas

            elif action == "briefing_diario":  # v0.11
                res = memoria.briefing_diario(calendar, tasks_mgr)
                response_payload["message"] = res.get("texto", "")
                response_payload["briefing"] = res.get("datos", {})

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

            # v0.11: registrar en memoria de conversación (contexto futuro)
            memoria.registrar_interaccion(message, action, response_payload.get("message", ""))

            self._send_json(200, response_payload)
            return

        if url_path == "/api/tasks":
            title = payload.get("title", "").strip()
            priority = int(payload.get("priority", 2))
            due_date = payload.get("due_date") or None
            res = tasks_mgr.add_task(title=title, priority=priority, due_date=due_date)
            self._send_json(200, res)
            return

        if url_path == "/api/tasks/complete":
            query = payload.get("query", "").strip()
            res = tasks_mgr.complete_task(query)
            self._send_json(200, res)
            return

        if url_path == "/api/notas":  # v0.11
            texto = payload.get("texto", "").strip()
            if not texto:
                self._send_json(400, {"status": "error", "message": "Nota vacía"})
                return
            self._send_json(200, memoria.crear_nota(texto, fuente=payload.get("fuente", "panel")))
            return

        if url_path == "/api/sync/calendario":  # v0.10: bidireccional
            self._send_json(200, tasks_mgr.sincronizar_calendario())
            return

        if url_path == "/api/audio/youtube":
            query = payload.get("query", "lofi beats")
            res = audio_engine.search_youtube(query)
            self._send_json(200, res)
            return

        if url_path == "/api/calendario/confirmar":
            summary = payload.get("summary", "Evento")
            start_time = payload.get("start_time")
            end_time = payload.get("end_time")
            res = calendar.create_event(
                summary=summary,
                start_time=start_time,
                end_time=end_time,
                description=payload.get("description", ""),
                location=payload.get("location", ""),
            )
            self._send_json(200, {
                "status": "ok",
                "message": res.get("message", f"¡Listo! Agendé '{summary}' en Google Calendar."),
                "event": res
            })
            return

        if url_path == "/api/calendario/cancelar":
            self._send_json(200, {
                "status": "ok",
                "message": "Agendamiento cancelado. No se creó ningún evento.",
            })
            return

        self._send_json(404, {"status": "error", "message": "Ruta no encontrada"})

    # ---------- DELETE ----------
    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        url_path = parsed.path

        if url_path.startswith("/api/"):
            if not self._origen_permitido():
                self._rechazar_origen()
                return

        # /api/notas?id=123  o  /api/notas/123
        if url_path == "/api/notas" or url_path.startswith("/api/notas/"):
            nota_id = None
            params = urllib.parse.parse_qs(parsed.query)
            if params.get("id"):
                nota_id = params["id"][0]
            else:
                parte = url_path.rstrip("/").rsplit("/", 1)[-1]
                if parte.isdigit():
                    nota_id = parte
            if not nota_id or not str(nota_id).isdigit():
                self._send_json(400, {"status": "error", "message": "Falta el id de la nota"})
                return
            self._send_json(200, memoria.eliminar_nota(int(nota_id)))
            return

        self._send_json(404, {"status": "error", "message": "Ruta no encontrada"})

    # ---------- Estado del sistema (v0.12) ----------
    def _estado_salud(self) -> dict:
        try:
            cache_tts = len(list((tts.CACHE_DIR).glob("*.mp3")))
        except Exception:
            cache_tts = 0
        return {
            "status": "ok",
            "version": _version(),
            "uptime_seg": round(time.time() - _INICIO, 1),
            "voz": {
                "tts_disponible": tts.listar_perfiles() != {},
                "perfil_activo": tts.perfil_actual(),
                "audios_en_cache": cache_tts,
            },
            "groq_configurado": bool(router.groq_api_key),
            "calendario_autenticado": calendar.is_authenticated(),
            "vikunja_configurado": bool(os.getenv("VIKUNJA_TOKEN", "").strip()),
            "herramientas": len(herramientas.nombres()),
            "tareas_pendientes": len(tasks_mgr.list_tasks(filter_done=False)),
            "notas_guardadas": memoria.contar_notas(),
            "alarmas_activas": len(timer_mgr.list_active_timers()),
        }

    def _send_json(self, code: int, data: Any):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Silenciar logs verbosos en consola


def start_server():
    version = _version()
    print("\n" + "=" * 65, flush=True)
    print(f"🚀 PANEL DEL ASISTENTE TDAH v{version}", flush=True)
    print(f"🔗 Interfaz disponible en: http://localhost:{PORT}", flush=True)
    print("• Google Calendar & Tasks: Sincronización dual activa", flush=True)
    print("• Vikunja: se configura vía .env (VIKUNJA_URL / VIKUNJA_TOKEN)", flush=True)
    print("• Audio Engine: YouTube streaming + Ruido Marrón/Blanco activo", flush=True)
    print("• Memoria: notas + briefing diario + contexto de conversación", flush=True)
    print("• Registro de herramientas MCP-ready: " + str(len(herramientas.nombres())), flush=True)
    print("• Voz neuronal edge-tts: " + (
        "activa" if tts.listar_perfiles() else "no disponible (pip install edge-tts)"
    ), flush=True)
    print("=" * 65 + "\n", flush=True)

    # ThreadingHTTPServer: la síntesis de voz o YouTube no bloquean la UI
    server = ThreadingHTTPServer(("localhost", PORT), AssistantHTTPHandler)
    server.serve_forever()


if __name__ == "__main__":
    start_server()
