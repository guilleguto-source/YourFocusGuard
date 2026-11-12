"""Memoria del Asistente TDAH — "segundo cerebro" ligero (v0.11).

Inspirado en la idea de Khoj (second brain personal), pero sin bases de
datos vectoriales ni dependencias nuevas: un solo archivo JSON local
(`data/memoria.json`) con dos secciones:

1. **Notas rápidas**: captura instantánea de ideas, códigos, recordatorios
   ("anota que la reunión cambió de sala"). Búsqueda por palabras clave
   tolerante a acentos y mayúsculas.
2. **Interacciones**: registro de lo último que le dijiste al asistente y
   qué hizo, para darle contexto en la conversación ("¿qué estaba haciendo?").

Todo es thread-safe (el servidor es multi-hilo) y con rotación automática
para que el archivo no crezca sin control.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional

from utilidades import normalizar_texto, formatear_fecha_es, saludo_por_hora

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORIA_FILE = os.path.join(BASE_DIR, "data", "memoria.json")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

MAX_NOTAS = 200
MAX_INTERACCIONES = 300

#: Palabras vacías que no puntúan en las búsquedas
STOPWORDS_ES = {
    "de", "la", "el", "los", "las", "que", "y", "a", "en", "mi", "mis",
    "un", "una", "del", "al", "es", "por", "para", "con", "sobre", "me",
    "lo", "se", "su", "sus", "como", "mas", "más", "muy", "ya", "o", "u",
}

_bloqueo = threading.Lock()


def _cargar() -> Dict[str, list]:
    if not os.path.exists(MEMORIA_FILE):
        return {"notas": [], "interacciones": []}
    try:
        with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "notas": data.get("notas", []),
            "interacciones": data.get("interacciones", []),
        }
    except Exception:
        return {"notas": [], "interacciones": []}


def _guardar(data: Dict[str, list]) -> None:
    os.makedirs(os.path.dirname(MEMORIA_FILE), exist_ok=True)
    with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _limites() -> Dict[str, int]:
    """Lee max_notas / max_interacciones de config.json (con defaults)."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        mem = cfg.get("memoria", {})
        return {
            "notas": int(mem.get("max_notas", MAX_NOTAS)),
            "interacciones": int(mem.get("max_interacciones", MAX_INTERACCIONES)),
        }
    except Exception:
        return {"notas": MAX_NOTAS, "interacciones": MAX_INTERACCIONES}


# ---------------------------------------------------------------------------
# NOTAS
# ---------------------------------------------------------------------------

def crear_nota(texto: str, fuente: str = "texto") -> Dict[str, Any]:
    """Guarda una nota rápida. Devuelve el registro creado."""
    texto = (texto or "").strip()
    if not texto:
        return {"status": "error", "message": "La nota está vacía."}

    nota = {
        "id": int(datetime.now().timestamp() * 1000),
        "texto": texto,
        "fuente": fuente,  # "texto" | "voz" | "panel"
        "creado": datetime.now().isoformat(),
    }
    with _bloqueo:
        data = _cargar()
        data["notas"].append(nota)
        limite = _limites()["notas"]
        if len(data["notas"]) > limite:
            data["notas"] = data["notas"][-limite:]
        _guardar(data)

    return {
        "status": "ok",
        "message": "Nota guardada en tu memoria.",
        "nota": nota,
    }


def listar_notas(limite: int = 50) -> List[Dict[str, Any]]:
    """Devuelve las últimas `limite` notas (más recientes primero)."""
    with _bloqueo:
        data = _cargar()
    return list(reversed(data["notas"]))[:limite]


def eliminar_nota(nota_id: int) -> Dict[str, Any]:
    with _bloqueo:
        data = _cargar()
        antes = len(data["notas"])
        data["notas"] = [n for n in data["notas"] if n.get("id") != nota_id]
        if len(data["notas"]) == antes:
            return {"status": "not_found", "message": f"No existe la nota {nota_id}."}
        _guardar(data)
    return {"status": "ok", "message": "Nota eliminada."}


def _tokens(texto: str) -> List[str]:
    """Palabras relevantes: minúsculas, sin acentos y SIN puntuación pegada.

    ("¿la puerta?" -> ["puerta"], no ["puerta?"])
    """
    import re

    normalizado = normalizar_texto(texto)
    return [
        t for t in re.findall(r"[a-z0-9]+", normalizado)
        if t and t not in STOPWORDS_ES
    ]


def buscar_notas(consulta: str, limite: int = 8) -> List[Dict[str, Any]]:
    """Búsqueda por palabras clave: puntúa cuántos términos coinciden.

    Tolerante a mayúsculas, acentos y palabras vacías ("¿qué anoté de la
    puerta?" encuentra la nota "código de la PUERTA: 1234").
    """
    q_tokens = _tokens(consulta)
    if not q_tokens:
        return []

    with _bloqueo:
        data = _cargar()

    resultados: List[tuple] = []
    for n in reversed(data["notas"]):  # recientes primero en caso de empate
        texto_norm = normalizar_texto(n.get("texto", ""))
        tokens_nota = set(_tokens(n.get("texto", "")))
        score = sum(1 for t in q_tokens if t in tokens_nota)
        # coincidencia parcial (substring) vale medio punto
        if score == 0 and any(t in texto_norm for t in q_tokens):
            score = 0.5
        if score > 0:
            resultados.append((score, n))

    resultados.sort(key=lambda par: -par[0])
    return [n for _, n in resultados[:limite]]


def contar_notas() -> int:
    with _bloqueo:
        return len(_cargar()["notas"])


# ---------------------------------------------------------------------------
# INTERACCIONES (memoria de conversación)
# ---------------------------------------------------------------------------

def registrar_interaccion(texto_usuario: str, accion: str, respuesta: str = "") -> None:
    """Guarda la última orden del usuario y lo que hizo el asistente."""
    registro = {
        "ts": datetime.now().isoformat(),
        "texto": (texto_usuario or "")[:200],
        "accion": accion or "charla",
        "respuesta": (respuesta or "")[:200],
    }
    try:
        with _bloqueo:
            data = _cargar()
            data["interacciones"].append(registro)
            limite = _limites()["interacciones"]
            if len(data["interacciones"]) > limite:
                data["interacciones"] = data["interacciones"][-limite:]
            _guardar(data)
    except Exception as e:
        logger.warning("No se pudo registrar la interacción: %s", e)


def contexto_reciente(n: int = 6) -> List[Dict[str, Any]]:
    """Devuelve las últimas n interacciones (para inyectarlas al prompt del LLM)."""
    with _bloqueo:
        data = _cargar()
    ult = data["interacciones"][-n:]
    out = []
    for r in ult:
        try:
            hora = datetime.fromisoformat(r["ts"]).strftime("%H:%M")
        except Exception:
            hora = "??:??"
        out.append({
            "hora": hora,
            "texto": r.get("texto", ""),
            "accion": r.get("accion", ""),
        })
    return out


def contexto_reciente_texto(n: int = 6) -> str:
    """Contexto formateado para el prompt del router (o '' si no hay nada)."""
    ctx = contexto_reciente(n)
    if not ctx:
        return ""
    lineas = [
        f"- [{c['hora']}] dijo: \"{c['texto']}\" -> {c['accion']}"
        for c in ctx
    ]
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# BRIEFING DIARIO (v0.11)
# ---------------------------------------------------------------------------

def briefing_diario(calendar, tasks_mgr) -> Dict[str, Any]:
    """Resumen hablado del día: fecha, eventos, tareas y notas.

    `calendar` y `tasks_mgr` se inyectan (no se importan aquí) para evitar
    dependencias circulares. Ambos degradan con elegancia si no hay conexión.
    """
    ahora = datetime.now()
    hoy_iso = ahora.strftime("%Y-%m-%d")
    partes: List[str] = []

    partes.append(f"{saludo_por_hora(ahora)}. Hoy es {formatear_fecha_es(ahora)}.")

    # 1) Eventos de hoy en Google Calendar
    eventos_hoy = []
    try:
        for ev in calendar.listar_eventos(dias=1, max_resultados=25):
            inicio = ev.get("start_dt") or ""
            if inicio[:10] == hoy_iso:
                eventos_hoy.append(ev)
    except Exception as e:
        logger.warning("Briefing: no se pudieron leer eventos: %s", e)

    if eventos_hoy:
        partes.append(f"Tienes {len(eventos_hoy)} evento{'s' if len(eventos_hoy) != 1 else ''} hoy:")
        for ev in eventos_hoy[:5]:
            hora = (ev.get("start_dt") or "")[11:16]
            prefijo = f"a las {hora}, " if hora else ""
            partes.append(f"{prefijo}{ev['title']}.")
    else:
        partes.append("Hoy no tienes eventos en tu Google Calendar.")

    # 2) Tareas pendientes (urgentes primero)
    try:
        tareas = tasks_mgr.list_tasks(filter_done=False)
    except Exception:
        tareas = []
    if tareas:
        partes.append(f"Tienes {len(tareas)} tarea{'s' if len(tareas) != 1 else ''} pendiente{'s' if len(tareas) != 1 else ''}.")
        top = tareas[:5]
        partes.append("Lo más urgente:")
        for t in top:
            titulo = t["title"].rstrip(".")
            partes.append(f"{titulo}.")
        if len(tareas) > 5:
            partes.append(f"Y {len(tareas) - 5} más que puedes ver en el panel.")
    else:
        partes.append("No tienes tareas pendientes. ¡Todo al día!")

    # 3) Notas capturadas hoy
    notas_hoy = [
        n for n in listar_notas(limite=200)
        if (n.get("creado") or "")[:10] == hoy_iso
    ]
    if notas_hoy:
        partes.append(f"Hoy capturaste {len(notas_hoy)} nota{'s' if len(notas_hoy) != 1 else ''} en tu memoria.")
        for n in notas_hoy[:2]:
            partes.append(f"Anotaste: {n['texto'][:120]}.")

    # 4) Cierre motivacional corto
    partes.append("Recuerda: hecho es mejor que perfecto. ¡Un paso a la vez!")

    return {
        "status": "ok",
        "texto": " ".join(partes),
        "datos": {
            "fecha": formatear_fecha_es(ahora),
            "eventos": eventos_hoy,
            "tareas": tareas,
            "notas_hoy": len(notas_hoy),
        },
    }
