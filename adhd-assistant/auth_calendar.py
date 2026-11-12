import os
import sys

# Resolver SSL con certificados nativos de Windows
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

PORT = 8080
REDIRECT_URI = f"http://localhost:{PORT}/"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

auth_code_holder = {}


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in query_components:
            auth_code_holder["code"] = query_components["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <html>
            <head><title>Conexión Exitosa</title></head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; padding: 60px; background: #0f172a; color: #f8fafc;">
                <div style="max-width: 500px; margin: 0 auto; background: #1e293b; padding: 40px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                    <h1 style="color: #4ade80; font-size: 32px; margin-bottom: 12px;">✅ ¡Conexión Exitosa!</h1>
                    <p style="font-size: 18px; color: #cbd5e1; line-height: 1.5;">Tu Google Calendar ha sido vinculado correctamente con el Asistente TDAH.</p>
                    <p style="color: #94a3b8; font-size: 14px; margin-top: 24px;">Ya puedes cerrar esta pestaña y volver a la consola.</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Error: no se recibio codigo de autorizacion.")

    def log_message(self, format, *args):
        pass  # Silenciar logs internos del servidor HTTP


def run():
    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cfg = data.get("installed") or data.get("web")
    client_id = cfg["client_id"]
    client_secret = cfg["client_secret"]
    auth_uri = cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/auth")
    token_uri = cfg.get("token_uri", "https://oauth2.googleapis.com/token")

    # Parámetros directos de OAuth
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{auth_uri}?{urllib.parse.urlencode(params)}"

    print("🚀 Servidor local activo en http://localhost:8080/", flush=True)
    print("\n" + "=" * 70, flush=True)
    print("🔑 ENLACE DE AUTORIZACIÓN:", flush=True)
    print(auth_url, flush=True)
    print("=" * 70 + "\n", flush=True)

    try:
        os.system(f'start "" "{auth_url}"')
    except Exception:
        pass

    server = HTTPServer(("localhost", PORT), OAuthCallbackHandler)
    while "code" not in auth_code_holder:
        server.handle_request()
    server.server_close()

    code = auth_code_holder["code"]
    print("📥 Código de autorización recibido de Google. Canjeando token...", flush=True)

    token_payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    resp = requests.post(token_uri, data=token_payload, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Error canjeando token: {resp.text}", flush=True)
        return

    tokens = resp.json()
    creds_dict = {
        "token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_uri": token_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES,
        "universe_domain": "googleapis.com",
        "account": "",
    }

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(creds_dict, f, indent=2)

    print(f"✅ Token guardado permanentemente en: {TOKEN_FILE}", flush=True)

    # Ahora crear el evento para mañana en Google Calendar
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now()
    manana = now + timedelta(days=1)
    start_time = manana.strftime("%Y-%m-%dT10:00:00-05:00")
    end_time = manana.strftime("%Y-%m-%dT11:00:00-05:00")

    event_body = {
        "summary": "Evento Asistente TDAH (Cita Mañana)",
        "description": "Evento agendado automáticamente por el Asistente TDAH",
        "start": {
            "dateTime": start_time,
            "timeZone": "America/Guayaquil",
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "America/Guayaquil",
        },
    }

    print(f"⏳ Agendando en tu Google Calendar: {start_time}...", flush=True)
    event = service.events().insert(calendarId="primary", body=event_body).execute()

    print("\n" + "=" * 70, flush=True)
    print("🎉 ¡EVENTO CREADO EXITOSAMENTE EN TU GOOGLE CALENDAR!", flush=True)
    print(f"📌 Título: {event.get('summary')}", flush=True)
    print(f"⏰ Horario: {start_time} a {end_time}", flush=True)
    print(f"🔗 Enlace directo al evento: {event.get('htmlLink')}", flush=True)
    print("=" * 70 + "\n", flush=True)


if __name__ == "__main__":
    run()
