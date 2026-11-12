"""Registro central de herramientas del Asistente TDAH (v0.12).

Fuente ÚNICA de verdad para las capacidades del asistente:

- El **prompt del router** (router.py) genera sus categorías a partir de
  este registro — antes estaban duplicadas a mano en el prompt.
- `esquemas_mcp()` expone las mismas herramientas en formato
  Model Context Protocol (name / description / inputSchema), listo para
  cuando activemos el servidor MCP (fase siguiente a v0.12).
- `pruebas_automaticas.py` valida contra este registro.

Añadir una herramienta nueva = añadir una entrada aquí + su manejo en
server.py / main.py. Nada más que sincronizar a mano.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# REGISTRO
# ---------------------------------------------------------------------------

REGISTRO: Dict[str, Dict[str, Any]] = {
    "crear_evento": {
        "descripcion": "Agendar una cita o evento en Google Calendar con día y hora.",
        "parametros": {
            "summary": {"tipo": "string", "requerido": True, "descripcion": "Título del evento"},
            "start_time": {"tipo": "string", "requerido": True, "descripcion": "Inicio ISO 8601 con offset -05:00"},
            "end_time": {"tipo": "string", "requerido": False, "descripcion": "Fin ISO 8601 (opcional)"},
        },
        "ejemplos": ["cita con el dentista mañana a las 10", "agenda reunión el viernes 15:00"],
    },
    "tarea_crear": {
        "descripcion": "Anotar un pendiente/trabajo por hacer (opcionalmente con fecha límite).",
        "parametros": {
            "title": {"tipo": "string", "requerido": True, "descripcion": "Título de la tarea"},
            "priority": {"tipo": "integer", "requerido": False, "descripcion": "1=Baja, 2=Normal, 3=Alta, 4=Urgente"},
            "due_date": {"tipo": "string", "requerido": False, "descripcion": "Fecha límite ISO 8601 (opcional)"},
        },
        "ejemplos": ["tengo que entregar el informe", "nueva tarea comprar pan"],
    },
    "tarea_listar": {
        "descripcion": "Listar las tareas pendientes, urgentes primero.",
        "parametros": {},
        "ejemplos": ["qué me toca", "mis pendientes"],
    },
    "tarea_completar": {
        "descripcion": "Marcar una tarea como completada buscando por nombre o id.",
        "parametros": {
            "query": {"tipo": "string", "requerido": True, "descripcion": "Nombre o id de la tarea"},
        },
        "ejemplos": ["ya terminé el informe", "completar tarea comprar pan"],
    },
    "crear_alarma": {
        "descripcion": "Programar una alarma o temporizador en X horas/minutos/segundos.",
        "parametros": {
            "seconds": {"tipo": "number", "requerido": True, "descripcion": "Duración total en segundos"},
            "label": {"tipo": "string", "requerido": True, "descripcion": "Etiqueta de la alarma"},
        },
        "ejemplos": ["alarma en 25 minutos", "recuérdame en 2 horas que apague el horno"],
    },
    "nota_crear": {
        "descripcion": (
            "Guardar una NOTA de información pura para recordar después "
            "(no es tarea ni evento: códigos, ideas, datos)."
        ),
        "parametros": {
            "texto": {"tipo": "string", "requerido": True, "descripcion": "Contenido de la nota"},
        },
        "ejemplos": ["anota que el código de la puerta es 1234", "apunta la idea del podcast"],
    },
    "nota_buscar": {
        "descripcion": "Buscar en las notas guardadas del usuario por palabras clave.",
        "parametros": {
            "query": {"tipo": "string", "requerido": True, "descripcion": "Texto a buscar"},
        },
        "ejemplos": ["qué anoté de la puerta", "busca en mis notas el podcast"],
    },
    "briefing_diario": {
        "descripcion": "Dar el resumen del día: fecha, eventos de hoy, tareas urgentes y notas.",
        "parametros": {},
        "ejemplos": ["resumen del día", "cómo va mi día"],
    },
    "audio_youtube": {
        "descripcion": "Buscar y reproducir música/audio desde YouTube.",
        "parametros": {
            "query": {"tipo": "string", "requerido": True, "descripcion": "Qué buscar en YouTube"},
        },
        "ejemplos": ["pon música lofi", "reproduce Hans Zimmer"],
    },
    "audio_noise": {
        "descripcion": "Activar ruido de foco: marrón (profundo), blanco (aislante) o rosa (calma).",
        "parametros": {
            "noise_type": {"tipo": "string", "requerido": True, "descripcion": "brown | white | pink"},
        },
        "ejemplos": ["pon ruido marrón", "ruido blanco"],
    },
    "audio_stop": {
        "descripcion": "Detener toda la reproducción de audio.",
        "parametros": {},
        "ejemplos": ["para la música", "stop audio"],
    },
    "charla": {
        "descripcion": "Conversación, apoyo o acompañamiento (todo lo demás).",
        "parametros": {
            "response": {"tipo": "string", "requerido": False, "descripcion": "Respuesta breve 1-2 frases"},
        },
        "ejemplos": ["estoy cansado", "no puedo concentrarme"],
    },
}

#: Herramientas que el LLM clasifica directamente (las demás van por reglas
#: rápidas de 0 ms en router.py y no necesitan pasar por el prompt)
CLASIFICABLES_POR_LLM = ["crear_evento", "tarea_crear", "nota_crear", "charla"]


# ---------------------------------------------------------------------------
# API DEL REGISTRO
# ---------------------------------------------------------------------------

def nombres() -> List[str]:
    return list(REGISTRO.keys())


def obtener(nombre: str) -> Optional[Dict[str, Any]]:
    return REGISTRO.get(nombre)


def definiciones_para_llm() -> str:
    """Bloque de texto con las categorías que el LLM debe clasificar.

    Solo incluye las herramientas `CLASIFICABLES_POR_LLM`; el resto se
    resuelve con reglas rápidas locales (0 ms, sin llamada a la API).
    """
    lineas = []
    for i, nombre in enumerate(CLASIFICABLES_POR_LLM, start=1):
        h = REGISTRO[nombre]
        campos = ", ".join(f'"{p}": ...' for p in h["parametros"])
        ejemplo = h["ejemplos"][0] if h["ejemplos"] else ""
        plantilla = '{"action": "%s"' % nombre
        if campos:
            plantilla += ", " + campos
        plantilla += "}"
        lineas.append(
            f'{i}. {h["descripcion"]} (ej: "{ejemplo}") -> responde {plantilla}'
        )
    return "\n".join(lineas)


def esquemas_mcp() -> List[Dict[str, Any]]:
    """Definiciones en formato Model Context Protocol (fase MCP).

    Cada entrada sigue la especificación de tools de MCP:
    {name, description, inputSchema}.
    """
    salida = []
    for nombre, h in REGISTRO.items():
        propiedades = {}
        requeridos = []
        for p, info in h["parametros"].items():
            propiedades[p] = {
                "type": info["tipo"],
                "description": info["descripcion"],
            }
            if info.get("requerido"):
                requeridos.append(p)
        salida.append({
            "name": nombre,
            "description": h["descripcion"],
            "inputSchema": {
                "type": "object",
                "properties": propiedades,
                "required": requeridos,
            },
        })
    return salida


def validar(nombre: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Validación básica: requeridos presentes y tipos correctos.

    Devuelve {"ok": True} o {"ok": False, "message": "..."}.
    """
    h = REGISTRO.get(nombre)
    if not h:
        return {"ok": False, "message": f"Herramienta desconocida: {nombre}"}

    for p, info in h["parametros"].items():
        if info.get("requerido") and (params.get(p) is None or params.get(p) == ""):
            return {"ok": False, "message": f"Falta el parámetro requerido '{p}' en {nombre}"}

        valor = params.get(p)
        if valor is None or valor == "":
            continue
        tipo = info["tipo"]
        if tipo == "string" and not isinstance(valor, str):
            return {"ok": False, "message": f"'{p}' debe ser texto"}
        if tipo == "integer" and not isinstance(valor, int):
            try:
                int(valor)
            except (TypeError, ValueError):
                return {"ok": False, "message": f"'{p}' debe ser entero"}
        if tipo == "number" and not isinstance(valor, (int, float)):
            try:
                float(valor)
            except (TypeError, ValueError):
                return {"ok": False, "message": f"'{p}' debe ser número"}
    return {"ok": True}
