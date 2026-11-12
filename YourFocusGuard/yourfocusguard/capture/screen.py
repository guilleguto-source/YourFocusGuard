"""Captura de pantalla con mss, reducción y JPEG solo en RAM.

Privacidad por construcción (blueprint, cap. 7): la imagen jamás toca el
disco; vive como ``bytes`` en la FIFO y se sobreescribe en <= 75 s.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)


class ScreenCaptureError(RuntimeError):
    """No se pudo capturar la pantalla (sin monitor, sesión remota, permisos...)."""


def grab_screen_jpeg(
    monitor: int = 1,
    escala_max_ancho: int = 1280,
    calidad_jpeg: int = 80,
) -> bytes:
    """Devuelve la captura del monitor indicado como JPEG ya reducido.

    El reescalado baja el coste de la API y la latencia sin perder legibilidad
    de la ventana activa (blueprint, cap. 4: 2.500-6.000 tokens por análisis).
    """
    import mss
    from PIL import Image

    try:
        with mss.mss() as sct:
            indice = max(0, min(monitor, len(sct.monitors)) - 1)  # monitors[0] = todo el escritorio
            raw = sct.grab(sct.monitors[indice])
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    except Exception as exc:  # mss lanza tipos distintos según el backend
        raise ScreenCaptureError(f"falló la captura de pantalla: {exc}") from exc

    if img.width > escala_max_ancho:
        alto = int(img.height * escala_max_ancho / img.width)
        img = img.resize((escala_max_ancho, alto), Image.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=calidad_jpeg)
    return buffer.getvalue()
