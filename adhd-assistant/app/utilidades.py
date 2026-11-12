"""Utilidades compartidas del Asistente TDAH.

Nacido en v0.10: formato de fechas/horas en español SIN depender del locale
del sistema (en Windows, `locale.setlocale(locale.LC_TIME, 'es_ES')` falla
casi siempre). Aquí los nombres de meses y días van fijos en el código.
"""

from __future__ import annotations

from datetime import datetime

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

DIAS_ES = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
]


def formatear_fecha_es(dt: datetime, con_dia_semana: bool = True) -> str:
    """'jueves 12 de noviembre de 2026' (o '12 de noviembre de 2026')."""
    base = f"{dt.day} de {MESES_ES[dt.month - 1]} de {dt.year}"
    if con_dia_semana:
        return f"{DIAS_ES[dt.weekday()]} {base}"
    return base


def formatear_hora_es(dt: datetime) -> str:
    """'15:04' en formato 24h (el que ya usa toda la UI)."""
    return dt.strftime("%H:%M")


def formatear_fecha_hora_es(dt: datetime) -> str:
    """'jueves 12 de noviembre de 2026, 15:04'."""
    return f"{formatear_fecha_es(dt)}, {formatear_hora_es(dt)}"


def saludo_por_hora(dt: datetime) -> str:
    """'Buenos días' / 'Buenas tardes' / 'Buenas noches' según la hora."""
    h = dt.hour
    if 5 <= h < 12:
        return "Buenos días"
    if 12 <= h < 19:
        return "Buenas tardes"
    return "Buenas noches"


def normalizar_texto(texto: str) -> str:
    """Minúsculas + sin acentos, para búsquedas tolerantes (v0.11)."""
    import unicodedata

    txt = (texto or "").lower().strip()
    txt = "".join(
        c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn"
    )
    return txt
