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
from typing import Dict, Any, Optional, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

#: Etiqueta que el asistente deja en la descripción de los eventos que crea
#: a partir de tareas. Sirve para identificarlos en la sincronización
#: bidireccional sin tocar los eventos propios del usuario.
ETIQUETA_ASISTENTE = "[asistente-tdah]"


def _iso_a_datetime(valor: Optional[str]) -> Optional[datetime]:
    """Convierte '2026-11-12T15:00:00-05:00' (o fecha simple) a datetime."""
    if not valor:
        return None
    try:
        limpio = valor.replace("Z", "")
        if "T" in limpio:
            limpio = limpio.split("+")[0]
            # quitar offset -05:00 del final
            if "-" in limpio[10:]:
                limpio = limpio[:10] + limpio[10:].rsplit("-", 1)[0]
        if "T" in limpio or ":" in limpio:
            return datetime.fromisoformat(limpio)
        return datetime.fromisoformat(limpio + "T09:00:00")
    except Exception:
        return None


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

    # ------------------------------------------------------------------
    # CREAR
    # ------------------------------------------------------------------
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
            dt_start = _iso_a_datetime(start_time)
            if dt_start:
                end_time = (dt_start + timedelta(hours=1)).isoformat()
            else:
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

    # ------------------------------------------------------------------
    # LISTAR / LEER (nuevo en v0.10)
    # ------------------------------------------------------------------
    @staticmethod
    def _extraer_inicio(ev: dict) -> Optional[str]:
        """Devuelve el dateTime (o date si es evento de día completo)."""
        inicio = ev.get("start") or {}
        return inicio.get("dateTime") or inicio.get("date")

    def listar_eventos(
        self,
        dias: int = 7,
        max_resultados: int = 15,
        texto: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lista los próximos eventos del calendario principal.

        `texto` filtra por coincidencia (case-insensitive) en el título.
        Devuelve [] si no hay conexión (jamás lanza excepción).
        """
        if not self.service:
            return []
        try:
            ahora = datetime.utcnow()
            fin = ahora + timedelta(days=dias)
            resp = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=ahora.isoformat() + "Z",
                    timeMax=fin.isoformat() + "Z",
                    maxResults=max_resultados,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            eventos = []
            for ev in resp.get("items", []):
                titulo = ev.get("summary", "(sin título)")
                if texto and texto.lower() not in titulo.lower():
                    continue
                dt_inicio = _iso_a_datetime(self._extraer_inicio(ev))
                dt_fin = _iso_a_datetime((ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"))
                eventos.append({
                    "id": ev.get("id"),
                    "title": titulo,
                    "start": self._extraer_inicio(ev),
                    "start_dt": dt_inicio.isoformat() if dt_inicio else None,
                    "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
                    "es_de_asistente": ETIQUETA_ASISTENTE in (ev.get("description") or ""),
                    "htmlLink": ev.get("htmlLink", ""),
                })
            return eventos
        except Exception as e:
            logger.warning(f"Error listando eventos: {e}")
            return []

    def obtener_evento(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Devuelve un evento por id, o None si no existe / sin conexión."""
        if not self.service or not event_id:
            return None
        try:
            ev = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            return {
                "id": ev.get("id"),
                "title": ev.get("summary", ""),
                "start": self._extraer_inicio(ev),
                "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
                "es_de_asistente": ETIQUETA_ASISTENTE in (ev.get("description") or ""),
            }
        except HttpError:
            return None  # 404/410: eliminado o cancelado
        except Exception as e:
            logger.warning(f"Error obteniendo evento {event_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # ACTUALIZAR / ELIMINAR (nuevo en v0.10)
    # ------------------------------------------------------------------
    def actualizar_evento(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        time_zone: str = "America/Guayaquil",
    ) -> Dict[str, Any]:
        """Modifica un evento existente (patch parcial)."""
        if not self.service:
            return {"status": "error", "message": "Sin conexión con Google Calendar."}

        try:
            ev = self.service.events().get(calendarId="primary", eventId=event_id).execute()
        except HttpError as err:
            return {"status": "error", "message": f"Evento no encontrado: {err.reason if hasattr(err, 'reason') else err}"}

        if summary:
            ev["summary"] = summary
        if start_time:
            if "T" in start_time:
                ev["start"] = {"dateTime": start_time, "timeZone": time_zone}
            else:
                ev["start"] = {"dateTime": f"{start_time}T09:00:00", "timeZone": time_zone}
        if end_time:
            if "T" in end_time:
                ev["end"] = {"dateTime": end_time, "timeZone": time_zone}
            else:
                ev["end"] = {"dateTime": f"{end_time}T10:00:00", "timeZone": time_zone}

        try:
            self.service.events().patch(calendarId="primary", eventId=event_id, body=ev).execute()
            return {"status": "ok", "message": f"Evento actualizado en Google Calendar."}
        except Exception as e:
            logger.warning(f"Error actualizando evento {event_id}: {e}")
            return {"status": "error", "message": f"No se pudo actualizar el evento: {e}"}

    def eliminar_evento(self, event_id: str) -> Dict[str, Any]:
        """Elimina un evento del calendario (tolerante si ya no existe)."""
        if not self.service:
            return {"status": "error", "message": "Sin conexión con Google Calendar."}
        try:
            self.service.events().delete(calendarId="primary", eventId=event_id).execute()
            return {"status": "ok", "message": "Evento eliminado de Google Calendar."}
        except HttpError as err:
            codigo = getattr(err, "resp", None)
            codigo = getattr(codigo, "status", 0) if codigo else 0
            if codigo in (404, 410):
                return {"status": "ok", "message": "El evento ya no existía en Google Calendar."}
            return {"status": "error", "message": f"No se pudo eliminar el evento: {err.reason if hasattr(err, 'reason') else err}"}
        except Exception as e:
            logger.warning(f"Error eliminando evento {event_id}: {e}")
            return {"status": "error", "message": f"No se pudo eliminar el evento: {e}"}
