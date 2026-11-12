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
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class Calendar:
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
    ):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.credentials_path = credentials_path or os.path.join(base_dir, "credentials.json")
        self.token_path = token_path or os.path.join(base_dir, "token.json")
        self.service = None
        self._authenticate()

    def _authenticate(self) -> None:
        """Autentica con OAuth 2.0 y guarda el token para reuso continuo."""
        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception as e:
                logger.warning(f"No se pudo cargar token existente: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Fallo al refrescar token: {e}. Se requiere nueva autenticación.")
                    creds = None

            if not creds:
                if not os.path.exists(self.credentials_path):
                    logger.error(f"Archivo de credenciales no encontrado en: {self.credentials_path}")
                    return

                with open(self.credentials_path, "r", encoding="utf-8") as f:
                    raw_cfg = json.load(f)

                # Si el tipo de credencial descargado fue 'web', adaptar para InstalledAppFlow
                if "web" in raw_cfg and "installed" not in raw_cfg:
                    cfg_installed = {
                        "installed": dict(
                            raw_cfg["web"],
                            redirect_uris=raw_cfg["web"].get("redirect_uris") or ["http://localhost"],
                        )
                    }
                    flow = InstalledAppFlow.from_client_config(cfg_installed, SCOPES)
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)

                print("\n" + "=" * 60)
                print("🔑 Se abrirá el navegador para autorizar Google Calendar una sola vez.")
                print("Por favor selecciona tu cuenta autorizada (guilleguto@gmail.com).")
                print("=" * 60 + "\n")
                creds = flow.run_local_server(port=0)

                with open(self.token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())

        try:
            self.service = build("calendar", "v3", credentials=creds)
            logger.info("Conexión con Google Calendar API establecida.")
        except Exception as e:
            logger.error(f"Error al construir servicio Calendar API: {e}")
            self.service = None

    def is_authenticated(self) -> bool:
        return self.service is not None

    def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: Optional[str] = None,
        description: str = "",
        location: str = "",
        time_zone: str = "America/Guayaquil",
    ) -> Dict[str, Any]:
        """Crea un evento en el calendario principal del usuario."""
        if not self.service:
            self._authenticate()
            if not self.service:
                return {
                    "status": "error",
                    "message": "No hay conexión autorizada con Google Calendar. Verifica credentials.json.",
                }

        # Calcular hora fin por defecto (+1 hora) si no se provee
        if not end_time:
            try:
                # Quitar 'Z' o offset si existe para parsear
                dt_clean = start_time.replace("Z", "")
                if "+" in dt_clean:
                    dt_clean = dt_clean.split("+")[0]
                elif "-" in dt_clean[10:]:
                    parts = dt_clean.rsplit("-", 1)
                    dt_clean = parts[0]
                dt_start = datetime.fromisoformat(dt_clean)
                dt_end = dt_start + timedelta(hours=1)
                end_time = dt_end.isoformat()
            except Exception:
                end_time = start_time

        event_body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {
                "dateTime": start_time if "T" in start_time else f"{start_time}T09:00:00",
                "timeZone": time_zone,
            },
            "end": {
                "dateTime": end_time if "T" in end_time else f"{end_time}T10:00:00",
                "timeZone": time_zone,
            },
        }

        try:
            created_event = (
                self.service.events()
                .insert(calendarId="primary", body=event_body)
                .execute()
            )
            html_link = created_event.get("htmlLink", "")
            event_id = created_event.get("id", "")
            return {
                "status": "ok",
                "message": f"Evento '{summary}' creado exitosamente en tu Google Calendar.",
                "id": event_id,
                "htmlLink": html_link,
                "start": start_time,
                "end": end_time,
            }
        except HttpError as err:
            logger.error(f"Error de Google Calendar API: {err}")
            return {
                "status": "error",
                "message": f"Error de Google API: {err.reason if hasattr(err, 'reason') else err}",
            }
        except Exception as e:
            logger.error(f"Error inesperado al crear evento: {e}")
            return {
                "status": "error",
                "message": f"Error inesperado: {str(e)}",
            }
