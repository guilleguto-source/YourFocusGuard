"""Prompt del sistema v1 (Apéndice B del blueprint, adaptado al nombre nuevo).

Versionado desde el día 1: cualquier cambio debe crear una v2 y bump de
``prompt_id`` para poder comparar la calidad de las versiones con datos reales.
Se envía siempre con temperatura 0 y modo de salida JSON estricto cuando el
proveedor lo ofrece, con un reintento único ante JSON inválido.
"""

PROMPT_ID = "v1"

SYSTEM_PROMPT_V1 = """Eres el módulo de evaluación de foco de YourFocusGuard.
Recibes: la tarea declarada, la app activa actual y una secuencia
ordenada de 2 a 5 capturas (pantalla y, opcionalmente, webcam),
cada una con su marca temporal.

Tu trabajo: decidir si el usuario MANTIENE la continuidad de la
tarea o lleva MÁS DE 30 SEGUNDOS distraído de forma sostenida
(redes, video, celular en mano, conversación, mirada fuera).

Reglas:
- Un frame aislado NUNCA es un desvío; exige continuidad temporal.
- Ignora las ventanas de la lista de exclusiones.
- Si dudas, responde desvio=false y baja la confianza.
- No inventes contenido que no esté en las imágenes.

Responde SOLO con JSON válido:
{
  "continuidad": true|false,
  "desvio":      true|false,
  "motivo": "redes|video|celular|conversacion|mirada|otro|ninguno",
  "app_detectada": "nombre de la app principal",
  "confianza":   0.0,
  "accion_sugerida": "nada|mascota|aviso|toast|voz"
}"""


def build_user_prompt(
    tarea: str,
    app_activa: str | None,
    marcas_temporales: list[str],
    historial: list[str],
) -> str:
    """Cuerpo del mensaje de usuario: tarea declarada, app activa y contexto."""
    tarea_txt = tarea.strip() if tarea and tarea.strip() else "(sin tarea declarada)"
    app_txt = app_activa or "(desconocida)"
    marcas = ", ".join(marcas_temporales) if marcas_temporales else "(sin marcas)"
    historial_txt = "\n".join(f"  - {linea}" for linea in historial) or "  - (vacío)"

    return (
        f"Tarea declarada por el usuario: {tarea_txt}\n"
        f"App activa actual: {app_txt}\n"
        f"Capturas adjuntas (la última es la actual): {marcas}\n"
        f"Historial reciente de la ventana FIFO:\n"
        f"{historial_txt}\n\n"
        "Evalúa la continuidad de la tarea y responde solo con el JSON definido."
    )
