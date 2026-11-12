import os
import sys
import logging
import threading
from typing import Dict, Any, Optional

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import yt_dlp

logger = logging.getLogger(__name__)


class AudioEngine:
    def __init__(self):
        self.current_track = None
        self.is_playing = False
        self.mode = "stopped"  # "youtube", "brown_noise", "white_noise", "stopped"

    def search_youtube(self, query: str) -> Dict[str, Any]:
        """Busca en YouTube y extrae el stream de audio directo para el reproductor."""
        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "nocheckcertificate": True,
            "default_search": "ytsearch1",
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                if not info or "entries" not in info or not info["entries"]:
                    return {"status": "error", "message": f"No se encontró audio para '{query}'."}

                entry = info["entries"][0]
                title = entry.get("title", query)
                stream_url = entry.get("url")
                webpage_url = entry.get("webpage_url")
                thumbnail = entry.get("thumbnail")

                self.current_track = {
                    "title": title,
                    "stream_url": stream_url,
                    "webpage_url": webpage_url,
                    "thumbnail": thumbnail,
                    "type": "youtube",
                }
                self.mode = "youtube"
                self.is_playing = True

                return {
                    "status": "ok",
                    "title": title,
                    "stream_url": stream_url,
                    "webpage_url": webpage_url,
                    "thumbnail": thumbnail,
                    "message": f"Reproduciendo: '{title}'",
                }
        except Exception as e:
            logger.error(f"Error extrayendo audio de YouTube: {e}")
            return {"status": "error", "message": f"Error buscando audio: {str(e)}"}

    def set_noise_mode(self, noise_type: str = "brown") -> Dict[str, Any]:
        """Activa generador de ruido de foco (brown, white, pink)."""
        clean_type = noise_type.lower()
        if "blanco" in clean_type or "white" in clean_type:
            tipo = "white"
            nombre = "Ruido Blanco (Concentración Pura)"
        elif "rosa" in clean_type or "pink" in clean_type:
            tipo = "pink"
            nombre = "Ruido Rosa (Lectura y Calma)"
        else:
            tipo = "brown"
            nombre = "Ruido Marrón (Enfoque Profundo TDAH)"

        self.current_track = {
            "title": nombre,
            "type": f"noise_{tipo}",
            "noise_type": tipo,
        }
        self.mode = f"noise_{tipo}"
        self.is_playing = True

        return {
            "status": "ok",
            "noise_type": tipo,
            "title": nombre,
            "message": f"Activado: {nombre}",
        }

    def stop(self) -> Dict[str, Any]:
        self.is_playing = False
        self.mode = "stopped"
        return {"status": "ok", "message": "Audio detenido."}

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_playing": self.is_playing,
            "mode": self.mode,
            "current_track": self.current_track,
        }
