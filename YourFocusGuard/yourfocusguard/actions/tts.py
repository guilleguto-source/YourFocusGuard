"""Voz neuronal de mascota estilo Muse (v0.8.2).

Utiliza Microsoft Edge Neural TTS con modulación de tono y velocidad
reproducido vía pygame.mixer, con catálogo de perfiles seleccionables,
caché local y reactividad de estados (IDLE -> SPEAKING -> IDLE).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import queue
import ssl
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

#: Directorios de audio
DATOS_DIR = Path(__file__).resolve().parent.parent.parent / "datos"
CACHE_DIR = DATOS_DIR / "tts_cache"
MUESTRAS_DIR = DATOS_DIR / "voces_muestra"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
MUESTRAS_DIR.mkdir(parents=True, exist_ok=True)

#: Catálogo oficial de 6 perfiles de voz para la mascota
PERFILES_VOZ = {
    "dalia_tierna": {
        "voz": "es-MX-DaliaNeural",
        "pitch": "+35Hz",
        "rate": "+10%",
        "nombre": "1. Dalia Tierna (Caricatura)",
        "archivo": "1_dalia_tierna.mp3",
    },
    "camila_dulce": {
        "voz": "es-PE-CamilaNeural",
        "pitch": "+30Hz",
        "rate": "+8%",
        "nombre": "2. Camila Mascota Dulce",
        "archivo": "2_camila_dulce.mp3",
    },
    "salome_energica": {
        "voz": "es-CO-SalomeNeural",
        "pitch": "+25Hz",
        "rate": "+12%",
        "nombre": "3. Salomé Enérgica",
        "archivo": "3_salome_energica.mp3",
    },
    "jorge_jovial": {
        "voz": "es-MX-JorgeNeural",
        "pitch": "+20Hz",
        "rate": "+10%",
        "nombre": "4. Jorge Mascota Jovial",
        "archivo": "4_jorge_jovial.mp3",
    },
    "dalia_natural": {
        "voz": "es-MX-DaliaNeural",
        "pitch": "+0Hz",
        "rate": "+0%",
        "nombre": "5. Dalia Humana Natural",
        "archivo": "5_dalia_natural.mp3",
    },
    "elvira_zen": {
        "voz": "es-ES-ElviraNeural",
        "pitch": "+5Hz",
        "rate": "-5%",
        "nombre": "6. Elvira Calma Zen",
        "archivo": "6_elvira_zen.mp3",
    },
}

_perfil_activo = "dalia_tierna"

# Verificación SSL segura con soporte de certifi y almacén de Windows (v0.8.3 O-01)
try:
    import edge_tts
    import edge_tts.communicate
    import edge_tts.constants
    import edge_tts.voices

    try:
        import certifi
        _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        _ssl_ctx = ssl.create_default_context()

    edge_tts.constants._SSL_CTX = _ssl_ctx
    edge_tts.communicate._SSL_CTX = _ssl_ctx
    edge_tts.voices._SSL_CTX = _ssl_ctx
except Exception as _exc:
    edge_tts = None  # type: ignore
    log.warning("edge-tts no disponible, fallback a voz básica: %s", _exc)

# Inicializar pygame.mixer para reproducción ultra-rápida y control de eventos
_pygame_iniciado = False
try:
    import pygame
    pygame.mixer.init()
    _pygame_iniciado = True
except Exception as _exc:
    log.warning("No se pudo iniciar pygame.mixer: %s", _exc)

_cola: "queue.Queue[str | None]" = queue.Queue(maxsize=10)
_hilo: threading.Thread | None = None
_candado = threading.Lock()
_hablando = False


def podar_cache_audio(max_archivos: int = 100, max_mb: float = 50.0) -> int:
    """Poda archivos de audio en CACHE_DIR según antigüedad (v0.8.3 O-07)."""
    try:
        archivos = sorted(CACHE_DIR.glob("*.mp3"), key=lambda f: f.stat().st_mtime)
        total_mb = sum(f.stat().st_size for f in archivos) / (1024 * 1024)
        eliminados = 0
        while (len(archivos) > max_archivos or total_mb > max_mb) and archivos:
            victima = archivos.pop(0)
            tam = victima.stat().st_size / (1024 * 1024)
            try:
                victima.unlink(missing_ok=True)
                total_mb -= tam
                eliminados += 1
            except Exception:
                pass
        if eliminados > 0:
            log.info("Poda de caché TTS: %d archivos antiguos eliminados (peso actual: %.2f MB)", eliminados, total_mb)
        return eliminados
    except Exception as exc:
        log.warning("Error en poda de caché TTS: %s", exc)
        return 0


# Poda preventiva de arranque
try:
    podar_cache_audio()
except Exception:
    pass


def fijar_perfil_voz(id_perfil: str) -> bool:
    """Cambia el perfil de voz activo para la mascota."""
    global _perfil_activo
    if id_perfil in PERFILES_VOZ:
        _perfil_activo = id_perfil
        log.info("Perfil de voz cambiado a: %s", id_perfil)
        return True
    return False


def obtener_perfil_actual() -> str:
    """Retorna el ID del perfil de voz activo."""
    return _perfil_activo


def listar_perfiles() -> list[tuple[str, str]]:
    """Retorna una lista de tuplas (id_perfil, nombre_humano)."""
    return [(k, v["nombre"]) for k, v in PERFILES_VOZ.items()]


def reproducir_muestra(id_perfil: str) -> None:
    """Reproduce inmediatamente el clip de muestra pre-generado del perfil."""
    cfg = PERFILES_VOZ.get(id_perfil)
    if not cfg:
        return
    ruta_mp3 = MUESTRAS_DIR / cfg["archivo"]
    if ruta_mp3.is_file():
        t = threading.Thread(target=_reproducir_audio, args=(ruta_mp3,), daemon=True)
        t.start()


def _hash_frase(texto: str) -> str:
    p = PERFILES_VOZ.get(_perfil_activo, PERFILES_VOZ["dalia_tierna"])
    clave = f"{texto}_{p['voz']}_{p['pitch']}_{p['rate']}"
    return hashlib.md5(clave.encode("utf-8")).hexdigest()[:16]


async def _generar_audio_edge(texto: str, ruta_salida: Path) -> bool:
    if edge_tts is None:
        return False
    try:
        p = PERFILES_VOZ.get(_perfil_activo, PERFILES_VOZ["dalia_tierna"])
        comunicador = edge_tts.Communicate(
            text=texto,
            voice=p["voz"],
            pitch=p["pitch"],
            rate=p["rate"],
        )
        await comunicador.save(str(ruta_salida))
        return ruta_salida.is_file() and ruta_salida.stat().st_size > 0
    except Exception as exc:
        log.warning("Error generando audio con edge-tts: %s", exc)
        return False


def _reproducir_audio(ruta_mp3: Path) -> None:
    global _hablando
    if not _pygame_iniciado or not ruta_mp3.is_file():
        return

    _hablando = True
    try:
        from yourfocusguard.core.events import EVT_PET_REACTION, publish
        publish(EVT_PET_REACTION, "speaking")
    except Exception:
        pass

    try:
        pygame.mixer.music.load(str(ruta_mp3))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy() and _hablando:
            time.sleep(0.05)
    except Exception as exc:
        log.warning("Error en reproducción con pygame: %s", exc)
    finally:
        _hablando = False
        try:
            from yourfocusguard.core.events import EVT_PET_REACTION, publish
            publish(EVT_PET_REACTION, "idle")
        except Exception:
            pass


def _fallback_sapi5(texto: str) -> None:
    """Fallback a voz de Windows en caso de fallo de red en edge-tts."""
    try:
        texto_seguro = texto.replace("'", " ").replace('"', " ").replace("`", " ").strip()
        ps_cmd = (
            f"[System.Reflection.Assembly]::LoadWithPartialName('System.Speech') | Out-Null; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Speak('{texto_seguro}')"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            timeout=10.0,
        )
    except Exception as exc:
        log.warning("Fallback SAPI5 falló: %s", exc)


def _bucle_voz() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        texto = _cola.get()
        if texto is None:
            break
        try:
            limpio = texto.strip()
            if not limpio:
                continue

            # Buscar en caché
            h = _hash_frase(limpio)
            ruta_audio = CACHE_DIR / f"{h}.mp3"

            if not ruta_audio.is_file() or ruta_audio.stat().st_size == 0:
                exito = loop.run_until_complete(_generar_audio_edge(limpio, ruta_audio))
                if not exito:
                    _fallback_sapi5(limpio)
                    continue

            # Reproducir con modulación del perfil activo
            _reproducir_audio(ruta_audio)

        except Exception as exc:
            log.warning("Fallo en bucle de voz de mascota: %s", exc)
        finally:
            _cola.task_done()


def _asegurar_hilo() -> None:
    global _hilo
    with _candado:
        if _hilo is None or not _hilo.is_alive():
            _hilo = threading.Thread(target=_bucle_voz, name="yfg-pet-voice-muse", daemon=True)
            _hilo.start()


def speak(texto: str, **kwargs) -> None:
    """Encola una frase para ser dicha por la mascota con la voz activa."""
    if not texto or not texto.strip():
        return
    _asegurar_hilo()
    try:
        _cola.put_nowait(texto.strip())
    except queue.Full:
        log.debug("Cola de voz llena, descartando frase")


def is_speaking() -> bool:
    """Indica si la mascota está hablando en este momento."""
    return _hablando


def parar() -> None:
    """Detiene la reproducción y el hilo de voz."""
    global _hilo
    detener_reproduccion()

    with _candado:
        if _hilo is not None and _hilo.is_alive():
            try:
                _cola.put_nowait(None)
            except queue.Full:
                pass
            _hilo.join(timeout=1.0)
            _hilo = None


def detener_reproduccion() -> None:
    """Detiene la reproducción activa inmediatamente (barge-in) sin apagar el hilo."""
    global _hablando
    try:
        if _pygame_iniciado:
            pygame.mixer.music.stop()
    except Exception:
        pass
    _hablando = False
    try:
        from yourfocusguard.core.events import EVT_PET_REACTION, publish
        publish(EVT_PET_REACTION, "idle")
    except Exception:
        pass


# Alias de compatibilidad para cierre limpio
cerrar = parar



def voces_disponibles() -> list[str]:
    return [v["nombre"] for v in PERFILES_VOZ.values()]
