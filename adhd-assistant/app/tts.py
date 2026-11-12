"""Voz neuronal gratuita para el Asistente TDAH (edge-tts).

Reemplaza la voz robotizada del navegador (window.speechSynthesis) por
voces neuronales de Microsoft Edge — las mismas de YourFocusGuard v0.8:

- 100% gratis, sin API key, sin límite de cuota
- Voces naturales en español (MX, CO, PE, ES)
- Caché en disco: los mensajes repetidos suenan al instante (0 ms)
- Fallback: si no hay internet devuelve None y el navegador usa su voz local

Uso:
    from tts import sintetizar, listar_perfiles, fijar_perfil
    ruta_mp3 = sintetizar("¡Listo! Tarea creada.")   # -> Path o None
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    import edge_tts
except Exception as _exc:  # pragma: no cover
    edge_tts = None  # type: ignore
    log.warning("edge-tts no instalado. Instala con: pip install edge-tts (%s)", _exc)

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "data" / "tts_cache"
CONFIG_PATH = BASE_DIR / "config.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

#: Catálogo de perfiles de voz (probado en YourFocusGuard v0.8, voces_muestra/)
PERFILES_VOZ = {
    "dalia_tierna": {
        "voz": "es-MX-DaliaNeural",
        "pitch": "+35Hz",
        "rate": "+10%",
        "nombre": "Dalia Tierna (caricatura)",
    },
    "camila_dulce": {
        "voz": "es-PE-CamilaNeural",
        "pitch": "+30Hz",
        "rate": "+8%",
        "nombre": "Camila Mascota Dulce",
    },
    "salome_energica": {
        "voz": "es-CO-SalomeNeural",
        "pitch": "+25Hz",
        "rate": "+12%",
        "nombre": "Salomé Enérgica (acento andino)",
    },
    "jorge_jovial": {
        "voz": "es-MX-JorgeNeural",
        "pitch": "+20Hz",
        "rate": "+10%",
        "nombre": "Jorge Mascota Jovial",
    },
    "dalia_natural": {
        "voz": "es-MX-DaliaNeural",
        "pitch": "+0Hz",
        "rate": "+0%",
        "nombre": "Dalia Humana Natural (recomendada)",
    },
    "elvira_zen": {
        "voz": "es-ES-ElviraNeural",
        "pitch": "+5Hz",
        "rate": "-5%",
        "nombre": "Elvira Calma Zen (España)",
    },
}

PERFIL_POR_DEFECTO = "dalia_natural"

#: Evita sintetizar el mismo texto dos veces en paralelo
_bloqueo = threading.Lock()


def _perfil_activo() -> str:
    """Resuelve el perfil activo: config.json -> variable de entorno -> default."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        perfil = cfg.get("voz", {}).get("perfil_activo", "")
        if perfil in PERFILES_VOZ:
            return perfil
    except Exception:
        pass
    perfil_env = os.getenv("ASISTENTE_VOZ", "")
    if perfil_env in PERFILES_VOZ:
        return perfil_env
    return PERFIL_POR_DEFECTO


def listar_perfiles() -> dict:
    """Devuelve {id_perfil: nombre_humano} para el selector de voz de la UI."""
    return {k: v["nombre"] for k, v in PERFILES_VOZ.items()}


def perfil_actual() -> str:
    return _perfil_activo()


def _hash_texto(texto: str, perfil_id: str) -> str:
    p = PERFILES_VOZ[perfil_id]
    clave = f"{texto}_{p['voz']}_{p['pitch']}_{p['rate']}"
    return hashlib.md5(clave.encode("utf-8")).hexdigest()[:24]


async def _sintetizar_edge(texto: str, p: dict, destino: Path) -> bool:
    comunicador = edge_tts.Communicate(
        text=texto, voice=p["voz"], pitch=p["pitch"], rate=p["rate"]
    )
    await comunicador.save(str(destino))
    return destino.is_file() and destino.stat().st_size > 0


def sintetizar(texto: str, perfil: Optional[str] = None) -> Optional[Path]:
    """Sintetiza `texto` y devuelve la ruta del MP3 (de caché si existe).

    Devuelve None si edge-tts no está disponible o no hay conexión.
    Es seguro llamarlo desde varios hilos del servidor.
    """
    if edge_tts is None or not texto or not texto.strip():
        return None

    perfil_id = perfil if perfil in PERFILES_VOZ else _perfil_activo()
    destino = CACHE_DIR / f"{_hash_texto(texto.strip(), perfil_id)}.mp3"

    # 1) Caché: respuesta instantánea
    if destino.is_file() and destino.stat().st_size > 0:
        return destino

    # 2) Sintetizar (con candado para no duplicar trabajo)
    with _bloqueo:
        if destino.is_file() and destino.stat().st_size > 0:
            return destino
        try:
            asyncio.run(_sintetizar_edge(texto.strip(), PERFILES_VOZ[perfil_id], destino))
        except Exception as exc:
            log.warning("edge-tts falló para '%s...': %s", texto[:40], exc)
            return None

    if destino.is_file() and destino.stat().st_size > 0:
        return destino
    return None
