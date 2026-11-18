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
import re
import logging
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import urllib.parse
import urllib.request
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
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PETS_DIR = os.path.join(ROOT_DIR, "YourFocusGuard", "yourfocusguard", "panel_static", "pets")
BESZEL_URL = os.getenv("BESZEL_URL", "http://192.168.1.20:8090")
YFG_PORT = int(os.getenv("YFG_PUERTO", "8756"))
YFG_URL = f"http://127.0.0.1:{YFG_PORT}"

#: Puerto configurable (8770 por defecto para convivir con PhoneBox en 8765)
PORT = int(os.getenv("ASISTENTE_PUERTO", "8770"))

#: Orígenes permitidos para la API local (la UI se sirve desde el mismo
#: servidor). Antes respondía Access-Control-Allow-Origin: * , lo que
#: permitía que CUALQUIER web abierta en el navegador leyera tus tareas
#: o enviara órdenes a http://localhost:8765.
ORIGENES_PERMITIDOS = {
    f"http://localhost:{PORT}",
    f"http://127.0.0.1:{PORT}",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
    "http://localhost:8766",
    "http://127.0.0.1:8766",
    "https://appassets.androidplatform.net",
    "null",
}

# ---------------------------------------------------------------------
# v0.12.1 — Endurecimiento + modo widget (inspirado en PhoneBox)
# ---------------------------------------------------------------------

#: Tope del cuerpo JSON en bytes (igual que el panel del guardián: 64 KB).
#: Antes el cuerpo se leía completo según Content-Length, sin límite.
MAX_CUERPO_BYTES = 64 * 1024

ARCHIVO_SESION = os.path.join(BASE_DIR, "data", "sesion_token.json")
ARCHIVO_BESZEL_AUTH = os.path.join(BASE_DIR, "data", "beszel_auth.json")


def _token_sesion() -> str:
    """Clave emparejada persistente para usar el asistente desde el celular.

    Equivalente a la 'paired key' de PhoneBox: se genera UNA vez, vive en
    data/sesion_token.json y es la única credencial que acepta el servidor
    para clientes que no son esta misma máquina. Loopback no la necesita.
    Borrar el archivo la regenera (desempareja todos los dispositivos).
    """
    try:
        os.makedirs(os.path.dirname(ARCHIVO_SESION), exist_ok=True)
        if os.path.isfile(ARCHIVO_SESION):
            with open(ARCHIVO_SESION, "r", encoding="utf-8") as f:
                tok = (json.load(f) or {}).get("token", "")
            if tok:
                return str(tok)
        import secrets
        tok = secrets.token_urlsafe(24)
        with open(ARCHIVO_SESION, "w", encoding="utf-8") as f:
            json.dump(
                {"token": tok, "creado": time.strftime("%Y-%m-%d %H:%M:%S")},
                f, indent=2,
            )
        return tok
    except Exception:
        return ""  # sin archivo no hay acceso LAN; loopback sigue funcionando


TOKEN_SESION = _token_sesion()

#: Modo red: por defecto el servidor SOLO escucha en localhost. Con
#: ASISTENTE_EXPUESTO_RED=1 escucha en todas las interfaces para que el
#: celular abra el widget por Wi-Fi (siempre con token emparejado).
EXPUESTO_RED = os.getenv("ASISTENTE_EXPUESTO_RED", "0") == "1"


def _ip_lan() -> str:
    """IP LAN principal de esta máquina ('' si no se puede determinar)."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))  # no envía tráfico: solo elige ruta
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return ""


IP_LAN = _ip_lan()

#: Hosts válidos para el header Host (anti DNS-rebinding)
_HOSTS_PERMITIDOS = {
    f"{h}:{PORT}" for h in ("localhost", "127.0.0.1", IP_LAN) if h
} | {h for h in ("localhost", "127.0.0.1", IP_LAN) if h}

#: Orígenes http válidos (localhost + la IP LAN para el widget del celular)
_ORIGENES_PERMITIDOS = set(ORIGENES_PERMITIDOS)
if IP_LAN:
    _ORIGENES_PERMITIDOS.add(f"http://{IP_LAN}:{PORT}")


def _qr_disponible() -> bool:
    try:
        import qrcode  # noqa: F401
        return True
    except Exception:
        return False


def _qr_ascii() -> str:
    """QR en texto (console) de la URL del widget. Requiere 'pip install qrcode'."""
    if not (EXPUESTO_RED and IP_LAN and TOKEN_SESION):
        return ""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(f"http://{IP_LAN}:{PORT}/widget?t={TOKEN_SESION}")
        qr.make()
        return qr.print_ascii(invert=True) or ""
    except Exception:
        return ""


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

    # ---------- Seguridad: Host / origen / token (v0.12.1) ----------
    def _cliente_local(self) -> bool:
        ip = self.client_address[0] if self.client_address else ""
        return ip in ("127.0.0.1", "::1", "localhost")

    def _token_recibido(self, parsed) -> str:
        """Token emparejado: ?t=..., header X-Token o cookie widget_token."""
        if parsed:
            t = urllib.parse.parse_qs(parsed.query).get("t", [""])[0]
            if t:
                return t
        xt = self.headers.get("X-Token", "")
        if xt:
            return xt
        cookie = self.headers.get("Cookie", "")
        if cookie:
            try:
                from http.cookies import SimpleCookie
                c = SimpleCookie(cookie)
                if "widget_token" in c:
                    return c["widget_token"].value
            except Exception:
                pass
        return ""

    def _token_valido(self, parsed) -> bool:
        return bool(TOKEN_SESION) and self._token_recibido(parsed) == TOKEN_SESION

    def _host_permitido(self) -> bool:
        host = self.headers.get("Host", "")
        if not host:
            return True  # cliente HTTP/1.0 sin Host: no aplica DNS-rebinding
        return host in _HOSTS_PERMITIDOS

    def _acceso_ok(self, parsed, url_path: str) -> bool:
        """Autorización unificada (v0.12.1).

        - Token válido: acceso concedido sin importar origen ni cliente.
        - Loopback (esta PC): la API exige Origin permitido si el navegador lo envía;
          los estáticos quedan libres.
        - Cliente remoto sin token: denegado.
        """
        if self._token_valido(parsed):
            return True
        if self._cliente_local():
            if url_path.startswith("/api/"):
                origin = self.headers.get("Origin")
                if not origin:
                    return True
                return origin in _ORIGENES_PERMITIDOS
            return True
        return False

    def _rechazar_origen(self):
        self.send_response(403)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"status": "error", "message": "Acceso no autorizado"}')

    def _servir_archivo_ui(self, nombre_archivo: str):
        ruta = os.path.join(UI_DIR, nombre_archivo)
        try:
            with open(ruta, "rb") as f:
                cuerpo = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _servir_widget_con_cookie(self, archivo: str = "widget.html"):
        """Sirve el widget móvil (panel o mascota) y fija la cookie del token emparejado."""
        ruta = os.path.join(UI_DIR, archivo)
        try:
            with open(ruta, "rb") as f:
                cuerpo = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        if TOKEN_SESION:
            self.send_header(
                "Set-Cookie",
                f"widget_token={TOKEN_SESION}; Path=/; HttpOnly; SameSite=Lax",
            )
        self.end_headers()
        self.wfile.write(cuerpo)

    def _proxy_a_yfg(self, parsed):
        url = f"{YFG_URL}{parsed.path}"
        if parsed.query:
            url += f"?{parsed.query}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ADHD-WidgetMascota"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self._send_json(502, {"status": "error", "message": f"YourFocusGuard no disponible: {e}"})

    def _proxy_post_a_yfg(self, url_path: str, payload: dict):
        url = f"{YFG_URL}{url_path}"
        try:
            cuerpo = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=cuerpo,
                headers={"Content-Type": "application/json", "User-Agent": "ADHD-WidgetMascota"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self._send_json(502, {"status": "error", "message": f"YourFocusGuard no disponible: {e}"})

    def _proxy_o_servir_pets(self, url_path: str):
        partes = [p for p in url_path.split("/") if p]
        if len(partes) >= 2:
            rel = os.path.join(*partes[1:])
            ruta_archivo = os.path.join(PETS_DIR, rel)
            if os.path.isfile(ruta_archivo):
                mime = "image/webp" if ruta_archivo.endswith(".webp") else "application/json" if ruta_archivo.endswith(".json") else "image/png"
                try:
                    with open(ruta_archivo, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except OSError:
                    pass
        parsed = urllib.parse.urlparse(self.path)
        self._proxy_a_yfg(parsed)

    def _proxy_beszel(self, parsed, method="GET", post_data=None):
        if parsed.path.startswith("/beszel"):
            rel_path = parsed.path[len("/beszel"):]
            if not rel_path:
                rel_path = "/"
        else:
            rel_path = parsed.path

        # SPA Fallback: todas las rutas HTML sirven index.html upstream
        is_html_route = method == "GET" and not any(rel_path.startswith(p) for p in ("/assets/", "/static/", "/api/"))
        if is_html_route:
            upstream_url = f"{BESZEL_URL}/"
        else:
            upstream_url = f"{BESZEL_URL}{rel_path}"
            if parsed.query:
                upstream_url += f"?{parsed.query}"

        req_headers = {}
        for h in ["Content-Type", "Authorization", "Cookie", "Accept", "Accept-Language", "User-Agent"]:
            val = self.headers.get(h)
            if val:
                req_headers[h] = val
        req_headers["Host"] = "192.168.1.20:8090"

        if "Authorization" not in req_headers and os.path.isfile(ARCHIVO_BESZEL_AUTH):
            try:
                with open(ARCHIVO_BESZEL_AUTH, "r", encoding="utf-8") as f:
                    ac = json.load(f)
                if "token" in ac:
                    req_headers["Authorization"] = ac["token"]
            except Exception:
                pass

        req = urllib.request.Request(upstream_url, data=post_data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                content_type = resp.headers.get("Content-Type", "text/html")
                if "text/html" in content_type:
                    html_str = data.decode("utf-8", errors="replace")
                    html_str = re.sub(
                        r'globalThis\.BESZEL\s*=\s*\{.*?\}',
                        'globalThis.BESZEL = {"BASE_PATH":"/beszel/","HUB_VERSION":"0.21.1","HUB_URL":""}',
                        html_str
                    )
                    html_str = html_str.replace('src="/assets/', 'src="/beszel/assets/')
                    html_str = html_str.replace('href="/assets/', 'href="/beszel/assets/')
                    html_str = html_str.replace('href="/static/', 'href="/beszel/static/')
                    html_str = html_str.replace('src="/static/', 'src="/beszel/static/')
                    auth_json = '""'
                    if os.path.isfile(ARCHIVO_BESZEL_AUTH):
                        try:
                            with open(ARCHIVO_BESZEL_AUTH, "r", encoding="utf-8") as f:
                                ac = json.load(f)
                            if "token" in ac:
                                auth_json = json.dumps(json.dumps({"token": ac["token"], "record": ac.get("record", {})}))
                        except Exception:
                            pass

                    polyfill = (
                        '<script>'
                        'if(location.pathname.endsWith("/login")||location.pathname.endsWith("/login/")){history.replaceState(null,"","/beszel/");}'
                        f'var _mem={{"ui-theme":"dark","pocketbase_auth":{auth_json}}};'
                        'globalThis._safeStorage={'
                        'getItem:function(k){return Object.prototype.hasOwnProperty.call(_mem,k)?_mem[k]:null;},'
                        'setItem:function(k,v){_mem[k]=String(v);},'
                        'removeItem:function(k){delete _mem[k];},'
                        'clear:function(){_mem={};},'
                        'key:function(i){return Object.keys(_mem)[i]||null;},'
                        'get length(){return Object.keys(_mem).length;}'
                        '};'
                        'try{Object.defineProperty(window,"localStorage",{value:globalThis._safeStorage,configurable:true,writable:true});}catch(e){}'
                        'try{Object.defineProperty(window,"sessionStorage",{value:globalThis._safeStorage,configurable:true,writable:true});}catch(e){}'
                        '</script>'
                        '<style>'
                        'html,body{background:#0e1220!important;color:#fff!important;overflow-x:hidden!important;}'
                        'div.container:not(.relative){display:none!important;}'
                        'div.container.relative>div:first-child>div:first-child{display:none!important;}'
                        'div.container.relative{padding:0!important;max-width:100%!important;}'
                        'div.container.relative>div:first-child{border:none!important;padding:4px!important;background:transparent!important;box-shadow:none!important;}'
                        '.grid.gap-4{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:10px!important;}'
                        '</style>'
                    )
                    html_str = html_str.replace("<head>", f"<head>{polyfill}")
                    data = html_str.encode("utf-8")
                elif "javascript" in content_type or rel_path.endswith(".js"):
                    js_str = data.decode("utf-8", errors="replace")
                    js_str = js_str.replace("window?.localStorage", "globalThis._safeStorage")
                    js_str = js_str.replace("window.localStorage", "globalThis._safeStorage")
                    js_str = js_str.replace("globalThis.localStorage", "globalThis._safeStorage")
                    js_str = re.sub(r'\blocalStorage\b', 'globalThis._safeStorage', js_str)
                    js_str = re.sub(r'\bsessionStorage\b', 'globalThis._safeStorage', js_str)
                    data = js_str.encode("utf-8")

                if "/auth-with-password" in parsed.path and method == "POST":
                    try:
                        auth_data = json.loads(data.decode("utf-8"))
                        if "token" in auth_data:
                            with open(ARCHIVO_BESZEL_AUTH, "w", encoding="utf-8") as f:
                                json.dump(auth_data, f, indent=2)
                            logger.info("Beszel: token auth guardado exitosamente")
                    except Exception:
                        pass

                self.send_response(resp.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.send_header("Access-Control-Allow-Methods", "*")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            err_data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(err_data)))
            self.end_headers()
            self.wfile.write(err_data)
        except Exception as e:
            self._send_json(502, {"status": "error", "message": f"Beszel no alcanzable (192.168.1.20:8090): {e}"})

    # ---------- GET ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        url_path = parsed.path

        # v0.12.1: validar el header Host en todas las rutas (DNS-rebinding)
        if not self._host_permitido():
            self._rechazar_origen()
            return

        # v0.12.1: entrada del widget (fija la cookie del token y sirve la página)
        if url_path in ("/widget", "/widget/"):
            if not self._acceso_ok(parsed, url_path):
                self._rechazar_origen()
                return
            self._servir_widget_con_cookie("widget.html")
            return

        if url_path in ("/widget-mascota", "/widget-mascota/"):
            if not self._acceso_ok(parsed, url_path):
                self._rechazar_origen()
                return
            self._servir_widget_con_cookie("widget-mascota.html")
            return

        if url_path.startswith("/pets/"):
            self._proxy_o_servir_pets(url_path)
            return

        if url_path == "/agent-sessions":
            self._servir_archivo_ui("agent_sessions.html")
            return

        if url_path == "/agent-hub":
            self._servir_archivo_ui("agent_hub.html")
            return

        if url_path == "/beszel" or url_path.startswith("/beszel/"):
            self._proxy_beszel(parsed, method="GET")
            return

        if url_path.startswith(("/api/collections/", "/api/beszel/", "/api/batch", "/api/settings", "/api/files/")):
            self._proxy_beszel(parsed, method="GET")
            return

        # Rutas de API o cliente remoto: verificar acceso antes de responder
        if url_path.startswith("/api/") or not self._cliente_local():
            if not self._acceso_ok(parsed, url_path):
                self._rechazar_origen()
                return

            if url_path.startswith("/api/pet/"):
                self._proxy_a_yfg(parsed)
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

            # ---- v0.12.1: widget del celular ----
            if url_path == "/api/widget_info":
                url_lan = (
                    f"http://{IP_LAN}:{PORT}/widget?t={TOKEN_SESION}"
                    if EXPUESTO_RED and IP_LAN and TOKEN_SESION else ""
                )
                self._send_json(200, {
                    "status": "ok",
                    "modo_red": "lan" if EXPUESTO_RED else "local",
                    "url_local": f"http://localhost:{PORT}/widget",
                    "url_lan": url_lan,
                    "token_configurado": bool(TOKEN_SESION),
                    "qr_disponible": _qr_disponible(),
                })
                return

            if url_path == "/api/widget/qr":
                self._send_json(200, {"status": "ok", "qr": _qr_ascii()})
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

            # ---- Multi-Agent Telemetry (Antigravity 2.0 + DeepSeek) ----
            if url_path == "/api/agents/state":
                try:
                    import agents_telemetry
                    self._send_json(200, agents_telemetry.get_all_state())
                except Exception as e:
                    logger.error("Error en telemetría de agentes: %s", e)
                    self._send_json(500, {"status": "error", "message": str(e)})
                return

            if url_path.startswith("/api/"):
                self._send_json(404, {"status": "error", "message": "Ruta no encontrada"})
                return
            # Cliente remoto (widget con token) pidiendo estáticos: sigue abajo

        # Archivos estáticos de la UI
        if url_path == "/":
            self.path = "/index.html"
        return super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        url_path = urllib.parse.urlparse(self.path).path

        if not self._host_permitido():
            self._rechazar_origen()
            return

        content_length = int(self.headers.get("Content-Length", 0) or 0)
        # v0.12.1: tope de cuerpo — antes se leía sin límite
        if content_length > MAX_CUERPO_BYTES:
            try:
                # Drenar para no enviar TCP RST en Windows antes de que el cliente lea el 413
                _ = self.rfile.read(min(content_length, 256 * 1024))
            except Exception:
                pass
            self._send_json(413, {"status": "error", "message": "Cuerpo demasiado grande (máx 64 KB)"})
            return
        post_data = self.rfile.read(content_length)

        # Rutas de Beszel (proxy transparente sin requerir token del asistente)
        if url_path.startswith("/beszel/") or url_path.startswith(("/api/collections/", "/api/beszel/", "/api/batch", "/api/settings", "/api/files/")):
            self._proxy_beszel(urllib.parse.urlparse(self.path), method="POST", post_data=post_data)
            return

        if url_path.startswith("/api/") or not self._cliente_local():
            if not self._acceso_ok(urllib.parse.urlparse(self.path), url_path):
                self._rechazar_origen()
                return

        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            payload = {}

        if url_path.startswith("/api/pet/") or url_path == "/api/control":
            self._proxy_post_a_yfg(url_path, payload)
            return

        if url_path == "/api/agents/approve":
            try:
                sig_file = os.path.join(
                    r"C:\Users\Guill\Documents\antigravity\blissful-einstein",
                    ".agents", "plans", "approval_signal.json"
                )
                os.makedirs(os.path.dirname(sig_file), exist_ok=True)
                with open(sig_file, "w", encoding="utf-8") as f:
                    json.dump({"approved": True, "ts": time.time(), "source": "phone"}, f, indent=2)

                # Notificar a PhoneBox de la confirmación
                try:
                    p_data = json.dumps({
                        "title": "✅ Plan Aprobado",
                        "message": "Aprobación enviada desde el teléfono. Ejecutando...",
                        "vibrate": True,
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        "http://127.0.0.1:8765/api/notify",
                        data=p_data,
                        headers={"Content-Type": "application/json"}
                    )
                    urllib.request.urlopen(req, timeout=2)
                except Exception:
                    pass
            except Exception as e:
                logger.error("Error guardando aprobación: %s", e)

            self._send_json(200, {"status": "ok", "message": "Plan aprobado"})
            return

        if url_path == "/api/phone/wake":
            try:
                import power_guard
                power_guard.wake_phone(seconds=35, switch_home=True)
            except Exception as e:
                logger.error("Error en wake: %s", e)
            self._send_json(200, {"status": "ok", "message": "Teléfono activado"})
            return

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

        if url_path == "/api/timers":  # v0.12.1: alarma rápida desde el widget
            try:
                minutos = int(payload.get("minutos", 0))
            except (TypeError, ValueError):
                minutos = 0
            label = str(payload.get("label", "Recordatorio")).strip()[:120]
            if not 1 <= minutos <= 24 * 60:
                self._send_json(400, {"status": "error", "message": "minutos debe estar entre 1 y 1440"})
                return
            res = timer_mgr.set_timer(duration_seconds=minutos * 60, label=label or "Recordatorio")
            self._send_json(200, res)
            return

        if url_path == "/api/tasks":
            title = str(payload.get("title", "")).strip()[:200]
            # v0.12.1: validación tipada — antes un priority no numérico
            # mataba el hilo con un 500 y traceback
            try:
                priority = int(payload.get("priority", 2))
            except (TypeError, ValueError):
                self._send_json(400, {"status": "error", "message": "priority debe ser un número entero (1-5)"})
                return
            if not 1 <= priority <= 5:
                self._send_json(400, {"status": "error", "message": "priority debe estar entre 1 y 5"})
                return
            due_date = payload.get("due_date") or None
            if due_date is not None and (not isinstance(due_date, str) or len(due_date) > 40):
                self._send_json(400, {"status": "error", "message": "due_date inválida"})
                return
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

        if not self._host_permitido():
            self._rechazar_origen()
            return

        if url_path.startswith("/api/") or not self._cliente_local():
            if not self._acceso_ok(parsed, url_path):
                self._rechazar_origen()
                return

        # v0.12.1: cancelar alarma desde el widget  /api/timers/123
        if url_path.startswith("/api/timers/"):
            parte = url_path.rstrip("/").rsplit("/", 1)[-1]
            if not parte.isdigit():
                self._send_json(400, {"status": "error", "message": "Falta el id de la alarma"})
                return
            self._send_json(200, timer_mgr.cancel_timer(int(parte)))
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

        if url_path.startswith("/beszel/") or url_path.startswith("/api/collections/") or url_path.startswith("/api/beszel/"):
            self._proxy_beszel(parsed, method="DELETE")
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
            "modo_red": "lan" if EXPUESTO_RED else "local",  # v0.12.1
            "calendario_autenticado": calendar.is_authenticated(),
            "vikunja_configurado": bool(os.getenv("VIKUNJA_TOKEN", "").strip()),
            "herramientas": len(herramientas.nombres()),
            "tareas_pendientes": len(tasks_mgr.list_tasks(filter_done=False)),
            "notas_guardadas": memoria.contar_notas(),
            "alarmas_activas": len(timer_mgr.list_active_timers()),
        }

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, PATCH, DELETE")
        self.end_headers()

    def do_PUT(self):
        url_path = urllib.parse.urlparse(self.path).path
        if url_path.startswith("/beszel/") or url_path.startswith("/api/collections/") or url_path.startswith("/api/beszel/"):
            content_length = int(self.headers.get("Content-Length", 0) or 0)
            post_data = self.rfile.read(content_length) if content_length > 0 else None
            self._proxy_beszel(urllib.parse.urlparse(self.path), method="PUT", post_data=post_data)
            return
        self.send_error(405)

    def do_PATCH(self):
        url_path = urllib.parse.urlparse(self.path).path
        if url_path.startswith("/beszel/") or url_path.startswith("/api/collections/") or url_path.startswith("/api/beszel/"):
            content_length = int(self.headers.get("Content-Length", 0) or 0)
            post_data = self.rfile.read(content_length) if content_length > 0 else None
            self._proxy_beszel(urllib.parse.urlparse(self.path), method="PATCH", post_data=post_data)
            return
        self.send_error(405)

    def _send_json(self, code: int, data: Any):
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

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
    print("• Widget para el celular: " + f"http://localhost:{PORT}/widget", flush=True)
    print("• Voz neuronal edge-tts: " + (
        "activa" if tts.listar_perfiles() else "no disponible (pip install edge-tts)"
    ), flush=True)
    try:
        import power_guard
        power_guard.start_guard()
        print("• PowerGuard: Monitor de inactividad y pulso inteligente ACTIVO", flush=True)
    except Exception as e:
        print(f"• PowerGuard: Error iniciando ({e})", flush=True)
    print("=" * 65 + "\n", flush=True)

    # v0.12.1: modo red opcional para el widget del celular (con token)
    host = "0.0.0.0" if EXPUESTO_RED else "localhost"
    if EXPUESTO_RED:
        print("• Modo red ACTIVADO: el celular puede entrar por Wi-Fi", flush=True)
        if IP_LAN and TOKEN_SESION:
            print(f"  → En el celular abre: http://{IP_LAN}:{PORT}/widget?t={TOKEN_SESION}", flush=True)
            qr = _qr_ascii()
            if qr:
                print(qr, flush=True)
        print("  (clave emparejada en data/sesion_token.json — bórrala para desemparejar)", flush=True)

    # ThreadingHTTPServer: la síntesis de voz o YouTube no bloquean la UI
    server = ThreadingHTTPServer((host, PORT), AssistantHTTPHandler)
    server.serve_forever()


if __name__ == "__main__":
    start_server()
