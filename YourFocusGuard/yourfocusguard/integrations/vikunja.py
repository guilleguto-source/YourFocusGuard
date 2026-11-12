"""Integración con Vikunja para gestión de tareas y agenda (v0.8.3 Fase 4).

Permite crear tareas en Vikunja vía API REST (POST /api/v1/projects/{id}/tasks).
Si Vikunja no está configurado o habilitado, devuelve False y permite el fallback
hacia el vault local (vault.py).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from yourfocusguard.config import VikunjaCfg

log = logging.getLogger("yourfocusguard.integrations.vikunja")

_PATRONES_NEGACION_AGENDA = [
    re.compile(r"\bno\s+(?:te\s+dije|quiero|agendes|programes|pongas|creas|crees|hagas)\b", re.IGNORECASE),
    re.compile(r"\b(?:no|sin)\s+agendar\b", re.IGNORECASE),
    re.compile(r"\bno\s+(?:lo\s+)?agendes\b", re.IGNORECASE),
    re.compile(r"\bno\s+dije\s+que\b", re.IGNORECASE),
    re.compile(r"\bpor\s+qu[eé]\s+(?:agendaste|programaste)\b", re.IGNORECASE),
    re.compile(r"\bqu[eé]\s+(?:tengo|hay)\s+(?:en\s+la\s+|agendado)\b", re.IGNORECASE),
]

_PATRONES_AGENDA = [
    re.compile(r"^\s*(?:oye\s+)?(?:einstein\s*,?\s*)?(?:agenda|agendar|programa|programar)\b", re.IGNORECASE),
    re.compile(r"\b(?:agenda|agendar|programa|programar)\s+(?:una|un|la|el|tarea|cita|reuni[oó]n|evento)\b", re.IGNORECASE),
    re.compile(r"\b(?:crear|agrega|agregar|nueva|nuevo)\s+(?:la\s+|el\s+|una\s+|un\s+)?(?:tarea|reuni[oó]n|cita)\b", re.IGNORECASE),
    re.compile(r"\b(?:tarea\s+para|recordar\s+tarea)\b", re.IGNORECASE),
    re.compile(r"\b(?:crear\s+en|agrega\s+a)\s+vikunja\b", re.IGNORECASE),
]

_PREFIJOS_LIMPIAR = [
    re.compile(r"^\s*(?:oye\s+)?(?:einstein\s*,?\s*)?", re.IGNORECASE),
    re.compile(r"^\s*(?:agenda|agendar|programa|programar)(?:\s+la)?(?:\s+tarea)?(?:\s+de)?\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:agrega|agregar|crea|crear|nueva|nuevo)\s+(?:la\s+)?(?:tarea|reunion|cita)(?:\s+de|\s+para)?\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:en\s+vikunja\s*,?\s*)", re.IGNORECASE),
]


def es_intencion_agenda(texto: str) -> bool:
    """Detecta si el comando verbal del usuario pide crear una tarea o evento de agenda."""
    if not texto or len(texto.strip()) < 4:
        return False
    limpio = texto.strip().lower()
    if any(neg.search(limpio) for neg in _PATRONES_NEGACION_AGENDA):
        return False
    return any(p.search(limpio) for p in _PATRONES_AGENDA)


def limpiar_texto_agenda(texto: str) -> str:
    """Limpia muletillas verbales para dejar el título limpio de la tarea."""
    res = texto.strip()
    for p in _PREFIJOS_LIMPIAR:
        res = p.sub("", res).strip()
    return res or texto.strip()


def crear_tarea(
    titulo: str,
    due_date_iso: str | None = None,
    descripcion: str = "",
    proyecto_id: int | None = None,
    cfg: VikunjaCfg | None = None,
) -> tuple[bool, str]:
    """Crea una tarea en Vikunja mediante su API REST.

    Retorna:
        tuple[bool, str]: (éxito, mensaje descriptivo)
    """
    if cfg is None or not cfg.habilitado:
        return False, "Vikunja no está habilitado en la configuración."

    if not cfg.url or not cfg.token:
        return False, "Vikunja no tiene URL o token configurado."

    pid = proyecto_id if proyecto_id is not None else cfg.proyecto_defecto_id
    url_base = cfg.url.rstrip("/")
    endpoint = f"{url_base}/api/v1/projects/{pid}/tasks"

    titulo_limpio = limpiar_texto_agenda(titulo)
    payload: dict[str, Any] = {"title": titulo_limpio}
    if due_date_iso:
        payload["due_date"] = due_date_iso
    if descripcion:
        payload["description"] = descripcion

    data_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {cfg.token}",
        "Content-Type": "application/json",
        "User-Agent": "YourFocusGuard/0.8.3",
    }

    try:
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            code = resp.getcode()
            if 200 <= code < 300:
                log.info("Tarea creada en Vikunja (HTTP %d): %s", code, titulo_limpio)
                return True, f"Tarea agendada en Vikunja: {titulo_limpio}"
            return False, f"Respuesta inesperada de Vikunja (HTTP {code})"
    except urllib.error.HTTPError as exc:
        log.warning("Error HTTP de Vikunja (%s): %s", exc.code, exc.reason)
        return False, f"Error HTTP {exc.code} al conectar con Vikunja"
    except urllib.error.URLError as exc:
        log.warning("No se pudo conectar con el servidor Vikunja: %s", exc.reason)
        return False, f"Servidor Vikunja no alcanzable: {exc.reason}"
    except Exception as exc:
        log.warning("Excepción inesperada al crear tarea en Vikunja: %s", exc)
        return False, f"Fallo al crear tarea en Vikunja: {exc}"
