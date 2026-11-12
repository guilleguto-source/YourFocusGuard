"""Controlador de música y ruido de fondo para concentración TDAH (v0.8.3 Fase 4).

Genera ruido marrón / blanco puro mediante numpy o reproduce flujos de concentración
usando canales dedicados de pygame.mixer sin interferir con la voz de la mascota.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from yourfocusguard.config import MusicaCfg

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore

log = logging.getLogger("yourfocusguard.actions.musica_foco")

CANAL_FOCO_INDEX = 1

def _normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFD", texto)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()

_PATRONES_INICIAR = [
    re.compile(r"\b(?:pon|reproduce|inicia|activar?|toca)\s+(?:la|el|un)?\s*(?:musica|ruido|sonido)\b"),
    re.compile(r"\b(?:ruido\s+marron|ruido\s+blanco|musica\s+(?:de\s+)?(?:foco|concentracion))\b"),
]

_PATRONES_DETENER = [
    re.compile(r"\b(?:para|deten|detener|apaga|apagar|quita|quitar|silencia|silenciar)\s+(?:la|el|un)?\s*(?:musica|ruido|sonido)\b"),
    re.compile(r"\b(?:silencio|apaga\s+musica|para\s+musica)\b"),
]

_PATRONES_VOLUMEN = [
    re.compile(r"\b(?:sube|aumenta|baja|disminuye)\s+(?:el\s+)?volumen\b"),
    re.compile(r"\bvolumen\s+(?:al?\s+)?(\d{1,3})%?\b"),
]

# Estado global del controlador
_reproduciendo: bool = False
_tipo_activo: str = "marron"
_volumen_actual: float = 0.5
_sonido_cache: Any = None


def es_intencion_musica(texto: str) -> bool:
    """Detecta si el comando verbal se relaciona con música o ruido de concentración."""
    if not texto or len(texto.strip()) < 3:
        return False
    limpio = _normalizar(texto.strip())
    return (
        any(p.search(limpio) for p in _PATRONES_INICIAR)
        or any(p.search(limpio) for p in _PATRONES_DETENER)
        or any(p.search(limpio) for p in _PATRONES_VOLUMEN)
    )


def es_intencion_detener_musica(texto: str) -> bool:
    """Detecta si el comando verbal pide apagar o silenciar la música/ruido."""
    if not texto:
        return False
    limpio = _normalizar(texto.strip())
    return any(p.search(limpio) for p in _PATRONES_DETENER)


def generar_ruido_marron(duracion_seg: float = 3.0, sample_rate: int = 44100) -> np.ndarray:
    """Genera una muestra cíclica continua de ruido marrón (Brownian noise) en PCM 16-bit estéreo."""
    n_samples = int(duracion_seg * sample_rate)
    blanco = np.random.normal(0, 1.0, n_samples)
    marron = np.cumsum(blanco)
    # Eliminar deriva lineal para enlace cíclico suave
    marron = marron - np.linspace(marron[0], marron[-1], n_samples)
    max_val = np.max(np.abs(marron))
    if max_val > 0:
        marron = (marron / max_val * 0.7)  # evitar saturación
    pcm = (marron * 32767).astype(np.int16)
    return np.column_stack([pcm, pcm])


def generar_ruido_blanco(duracion_seg: float = 3.0, sample_rate: int = 44100) -> np.ndarray:
    """Genera ruido blanco suave en PCM 16-bit estéreo."""
    n_samples = int(duracion_seg * sample_rate)
    blanco = np.random.normal(0, 0.2, n_samples)
    pcm = (blanco * 32767).astype(np.int16)
    return np.column_stack([pcm, pcm])


def _asegurar_mixer() -> bool:
    """Inicializa pygame.mixer si aún no está listo."""
    if pygame is None:
        return False
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        return True
    except Exception as exc:
        log.warning("No se pudo inicializar pygame.mixer para música de foco: %s", exc)
        return False


def iniciar_musica_foco(
    tipo: str = "marron",
    volumen: float | None = None,
    cfg: MusicaCfg | None = None,
) -> tuple[bool, str]:
    """Inicia la reproducción en bucle de ruido de foco en canal secundario."""
    global _reproduciendo, _tipo_activo, _volumen_actual, _sonido_cache

    if cfg is not None and not cfg.habilitado:
        return False, "La música de foco está desactivada en la configuración."

    if volumen is not None:
        _volumen_actual = max(0.0, min(1.0, float(volumen)))
    elif cfg is not None:
        _volumen_actual = max(0.0, min(1.0, float(cfg.volumen)))

    if not _asegurar_mixer():
        return False, "Dispositivo de audio o pygame no disponible."

    try:
        if tipo == "blanco":
            datos_audio = generar_ruido_blanco()
            nombre = "ruido blanco"
        else:
            datos_audio = generar_ruido_marron()
            nombre = "ruido marrón"

        canal = pygame.mixer.Channel(CANAL_FOCO_INDEX)
        _sonido_cache = pygame.sndarray.make_sound(datos_audio)
        canal.set_volume(_volumen_actual)
        canal.play(_sonido_cache, loops=-1)
        _reproduciendo = True
        _tipo_activo = tipo
        log.info("Música de foco iniciada (%s, vol=%.2f)", nombre, _volumen_actual)
        return True, f"Iniciando {nombre} para concentración."
    except Exception as exc:
        log.warning("Error iniciando música de foco: %s", exc)
        return False, f"Fallo al reproducir música: {exc}"


def detener_musica_foco() -> tuple[bool, str]:
    """Detiene la música o ruido de foco."""
    global _reproduciendo, _sonido_cache
    if not _reproduciendo:
        return True, "No había música de foco activa."

    try:
        if pygame and pygame.mixer.get_init():
            canal = pygame.mixer.Channel(CANAL_FOCO_INDEX)
            canal.stop()
        _reproduciendo = False
        _sonido_cache = None
        log.info("Música de foco detenida.")
        return True, "Música de foco detenida."
    except Exception as exc:
        log.warning("Error al detener música de foco: %s", exc)
        _reproduciendo = False
        return False, f"Error al detener música: {exc}"


def ajustar_volumen(volumen: float) -> tuple[bool, str]:
    """Ajusta el volumen del canal de música de foco (0.0 a 1.0)."""
    global _volumen_actual
    _volumen_actual = max(0.0, min(1.0, float(volumen)))
    try:
        if pygame and pygame.mixer.get_init():
            canal = pygame.mixer.Channel(CANAL_FOCO_INDEX)
            canal.set_volume(_volumen_actual)
        return True, f"Volumen ajustado al {int(_volumen_actual * 100)}%."
    except Exception as exc:
        return False, f"Error ajustando volumen: {exc}"


def estado_musica() -> dict[str, Any]:
    """Retorna el estado actual del controlador."""
    return {
        "activo": _reproduciendo,
        "tipo": _tipo_activo,
        "volumen": _volumen_actual,
    }
