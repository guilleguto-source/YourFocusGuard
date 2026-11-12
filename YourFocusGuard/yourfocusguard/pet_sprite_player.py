"""Extractor y reproductor de spritesheets WebP de OpenPets con Modo TDAH Suave (v0.8.1).

En modo normal o idle, la mascota mantiene un estado calmo:
- Reposo en frame 0 la mayor parte del tiempo.
- Micro-parpadeos o movimientos sutiles cada 5-8 segundos.
- Un movimiento más marcado o expresivo únicamente cada 2-3 minutos.
- Soporta 3 tamaños configurables: 'pequeño', 'normal', 'grande'.
"""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from PIL import Image, ImageTk

log = logging.getLogger(__name__)

FRAME_W = 192
FRAME_H = 208

TAMAÑOS_ESCALA = {
    "pequeño": 0.40,
    "normal": 0.55,
    "grande": 0.75,
}

ESTADOS_CONFIG = {
    "idle": {"fila": 0, "frames": 6, "delay_ms": 160},
    "running-right": {"fila": 1, "frames": 8, "delay_ms": 110},
    "running-left": {"fila": 2, "frames": 8, "delay_ms": 110},
    "waving": {"fila": 3, "frames": 4, "delay_ms": 160},
    "jumping": {"fila": 4, "frames": 5, "delay_ms": 140},
    "error": {"fila": 5, "frames": 8, "delay_ms": 130},
    "failed": {"fila": 5, "frames": 8, "delay_ms": 130},
    "waiting": {"fila": 6, "frames": 6, "delay_ms": 150},
    "thinking": {"fila": 6, "frames": 6, "delay_ms": 150},
    "running": {"fila": 7, "frames": 6, "delay_ms": 120},
    "working": {"fila": 8, "frames": 6, "delay_ms": 140},
    "review": {"fila": 8, "frames": 6, "delay_ms": 140},
    "speaking": {"fila": 3, "frames": 4, "delay_ms": 140},
    "listening": {"fila": 6, "frames": 6, "delay_ms": 180},
}


class SpriteSheetPlayer:
    """Carga un spritesheet de OpenPets y produce imágenes para Tkinter con timing suave."""

    def __init__(
        self,
        ruta_spritesheet: Path,
        tamaño: str = "normal",
        color_clave: str = "#000001",
        modo_tdah: bool = True,
    ) -> None:
        self.ruta = Path(ruta_spritesheet)
        self.tamaño = tamaño
        self.escala = TAMAÑOS_ESCALA.get(tamaño, 0.55)
        self.color_clave = color_clave
        self.modo_tdah = modo_tdah
        self._target_w = int(FRAME_W * self.escala)
        self._target_h = int(FRAME_H * self.escala)
        self._sheet: Image.Image | None = None
        self._cache_frames: dict[str, list[ImageTk.PhotoImage]] = {}

        # Estado del scheduler TDAH
        self._ultimo_parpadeo = time.time()
        self._ultimo_movimiento_largo = time.time()
        self._proximo_intervalo_parpadeo = random.uniform(5.0, 8.0)
        self._en_parpadeo = False
        self._en_movimiento_largo = False

        self._cargar()

    def cambiar_tamaño(self, nuevo_tamaño: str) -> None:
        if nuevo_tamaño in TAMAÑOS_ESCALA and nuevo_tamaño != self.tamaño:
            self.tamaño = nuevo_tamaño
            self.escala = TAMAÑOS_ESCALA[nuevo_tamaño]
            self._target_w = int(FRAME_W * self.escala)
            self._target_h = int(FRAME_H * self.escala)
            self._cache_frames.clear()

    @property
    def dimensiones(self) -> tuple[int, int]:
        return self._target_w, self._target_h

    def _cargar(self) -> None:
        if not self.ruta.is_file():
            log.warning("No existe el spritesheet en: %s", self.ruta)
            return
        try:
            self._sheet = Image.open(self.ruta).convert("RGBA")
        except Exception as exc:
            log.error("Error abriendo spritesheet %s: %s", self.ruta, exc)

    def obtener_frames(self, estado: str) -> tuple[list[ImageTk.PhotoImage], int]:
        estado_norm = (estado or "idle").lower()
        cfg = ESTADOS_CONFIG.get(estado_norm, ESTADOS_CONFIG["idle"])

        if estado_norm in self._cache_frames:
            return self._cache_frames[estado_norm], cfg["delay_ms"]

        if self._sheet is None:
            return [], cfg["delay_ms"]

        fila = cfg["fila"]
        num_frames = cfg["frames"]
        y0 = fila * FRAME_H
        y1 = y0 + FRAME_H

        frames_tk = []
        for i in range(num_frames):
            x0 = i * FRAME_W
            x1 = x0 + FRAME_W
            try:
                frame_crop = self._sheet.crop((x0, y0, x1, y1))
                frame_res = frame_crop.resize((self._target_w, self._target_h), Image.Resampling.LANCZOS)
                bg = Image.new("RGBA", (self._target_w, self._target_h), self.color_clave)
                bg.paste(frame_res, (0, 0), mask=frame_res)
                frame_final = bg.convert("RGB")
                frames_tk.append(ImageTk.PhotoImage(frame_final))
            except Exception as exc:
                log.debug("Error procesando frame %s de %s: %s", i, estado_norm, exc)

        self._cache_frames[estado_norm] = frames_tk
        return frames_tk, cfg["delay_ms"]

    def siguiente_frame_index(self, estado: str, frame_actual: int, total_frames: int) -> tuple[int, int]:
        """Calcula el siguiente frame y delay respetando el Modo TDAH Calmo."""
        if not self.modo_tdah or total_frames <= 1:
            return (frame_actual + 1) % max(1, total_frames), 150

        # Estados activos / habla / alerta siempre se mueven para llamar la atención requerida
        if estado in ("error", "failed", "waving", "speaking", "listening"):
            return (frame_actual + 1) % total_frames, 130

        ahora = time.time()

        # Comprobar si toca movimiento expresivo largo (cada 2 a 3 minutos)
        if not self._en_movimiento_largo and (ahora - self._ultimo_movimiento_largo) > 150.0:
            self._en_movimiento_largo = True
            self._ultimo_movimiento_largo = ahora
            return 1, 140

        if self._en_movimiento_largo:
            siguiente = frame_actual + 1
            if siguiente >= total_frames:
                self._en_movimiento_largo = False
                return 0, 500  # Vuelve al reposo
            return siguiente, 140

        # Comprobar si toca micro-parpadeo sutil (cada 5 a 8 segundos)
        if not self._en_parpadeo and (ahora - self._ultimo_parpadeo) > self._proximo_intervalo_parpadeo:
            self._en_parpadeo = True
            self._ultimo_parpadeo = ahora
            self._proximo_intervalo_parpadeo = random.uniform(5.0, 8.5)
            # Frame 1 suele ser el ojo entrecerrado
            return min(1, total_frames - 1), 160

        if self._en_parpadeo:
            self._en_parpadeo = False
            return 0, 500  # Vuelve al reposo quieto

        # Estado normal en reposo quieto (Frame 0 sin bailar todo el tiempo)
        return 0, 500
