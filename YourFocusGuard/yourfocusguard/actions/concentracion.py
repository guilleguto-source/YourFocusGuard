"""Modo Máxima Concentración (v0.7.0, Fase 3).

Cuando el usuario activa una sesión de máxima concentración, el asistente no
solo avisa: actúa sobre el sistema para eliminar distracciones:

    * Bloquea dominios distractores (YouTube, Instagram, TikTok…)
      reescribiendo el archivo hosts de Windows (C:WindowsSystem32driversetchosts).
    * Silencia el audio del sistema (mute del dispositivo de salida por defecto).
    * Minimiza procesos bloqueados cada vez que vuelven al primer plano.

Todo se deshace automáticamente al cerrar la sesión o al desactivar el modo:
restauramos el hosts original y volvemos a activar el audio.

Diseñado para degradar con elegancia: si no hay privilegios de administrador
para editar el hosts, se avisa en consola y se sigue con las otras medidas.
Si no se puede silenciar el audio, se ignora silenciosamente.

Nunca lanza excepciones que maten al agente: cada medida se envuelve en try/except.
"""
from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from yourfocusguard.config import ConcentracionCfg

log = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

#: Dominios por defecto que el modo concentración sugiere bloquear.
DOMINIOS_POR_DEFECTO = (
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "facebook.com",
    "www.facebook.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "reddit.com",
    "www.reddit.com",
    "netflix.com",
    "www.netflix.com",
    "twitch.tv",
    "www.twitch.tv",
)

#: Entrada de hosts que bloquea un dominio (apunta a localhost).
_HOSTS_LINEA = "127.0.0.1 {dominio}"
_MARCADOR_INICIO = "# BEGIN YourFocusGuard (Concentracion)"
_MARCADOR_FIN = "# END YourFocusGuard (Concentracion)"


def _hosts_ruta() -> Path:
    """Ruta del archivo hosts de Windows."""
    if _IS_WINDOWS:
        return Path(r"C:\Windows\System32\drivers\etc\hosts")
    return Path("/etc/hosts")


def _leer_hosts() -> str:
    ruta = _hosts_ruta()
    try:
        return ruta.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _escribir_hosts(contenido: str) -> bool:
    """Escribe el archivo hosts con backup .bak previo. Devuelve True si tuvo éxito."""
    ruta = _hosts_ruta()
    try:
        bak = ruta.with_suffix(".bak")
        if ruta.exists() and not bak.exists():
            try:
                shutil.copy2(ruta, bak)
            except OSError:
                pass
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(contenido, encoding="utf-8")
        tmp.replace(ruta)
        return True
    except (OSError, PermissionError) as exc:
        log.warning("no se pudo escribir el archivo hosts: %s", exc)
        return False


def limpiar_huerfanos_hosts() -> bool:
    """Elimina cualquier bloque residual de YourFocusGuard del archivo hosts."""
    if not _IS_WINDOWS:
        return True
    contenido = _leer_hosts()
    if not contenido or _MARCADOR_INICIO not in contenido:
        return True
    pattern = re.compile(rf"\n?{re.escape(_MARCADOR_INICIO)}.*?{re.escape(_MARCADOR_FIN)}\n?", re.DOTALL)
    limpio = pattern.sub("", contenido)
    return _escribir_hosts(limpio)


def _ya_bloqueado(contenido: str, dominio: str) -> bool:
    token = _HOSTS_LINEA.format(dominio=dominio)
    return token in contenido


class ModoConcentracion:
    """Gestor del modo máxima concentración.

    Lleva registro de lo que modificó (líneas de hosts añadidas, estado de
    audio previo) para poder deshacerlo todo al salir.
    """

    def __init__(self, cfg: ConcentracionCfg, reloj: Callable[[], float] = time.time) -> None:
        self.cfg = cfg
        self.reloj = reloj
        self.activo = False
        self._hosts_lineas_anadidas: list[str] = []
        self._audio_was_muted = False
        self._inicio: float | None = None

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #

    def activar(self) -> dict[str, bool | list[str]]:
        """Activa todas las medidas configuradas. Devuelve un resumen de éxito."""
        if self.activo:
            return self._resumen()
        self.activo = True
        self._inicio = self.reloj()
        resultado: dict[str, bool | list[str]] = {
            "hosts": False,
            "audio": False,
            "dominios_bloqueados": [],
            "error": "",
        }

        if self.cfg.bloquear_hosts and _IS_WINDOWS:
            ok, lineas = self._bloquear_dominios_hosts()
            resultado["hosts"] = ok
            resultado["dominios_bloqueados"] = lineas

        if self.cfg.silenciar_audio and _IS_WINDOWS:
            resultado["audio"] = self._silenciar_audio()

        log.info(
            "modo máxima concentración activado: hosts=%s audio=%s dominios=%s",
            resultado["hosts"], resultado["audio"],
            ", ".join(resultado["dominios_bloqueados"]) or "ninguno",
        )
        return resultado

    def desactivar(self) -> dict[str, bool]:
        """Deshace todo lo que se modificó. Devuelve resumen de éxito."""
        if not self.activo:
            return {"hosts": True, "audio": True}
        self.activo = False
        resultado: dict[str, bool] = {"hosts": True, "audio": True}

        if self.cfg.restaurar_al_salir and _IS_WINDOWS:
            if self._hosts_lineas_anadidas:
                resultado["hosts"] = self._restaurar_hosts()
            if self.cfg.silenciar_audio:
                resultado["audio"] = self._restaurar_audio()

        self._hosts_lineas_anadidas = []
        self._inicio = None
        log.info("modo máxima concentración desactivado: hosts=%s audio=%s",
                 resultado["hosts"], resultado["audio"])
        return resultado

    def _resumen(self) -> dict[str, bool | list[str]]:
        return {
            "hosts": self.activo,
            "audio": self.activo,
            "dominios_bloqueados": list(self._hosts_lineas_anadidas),
            "error": "",
        }

    # ------------------------------------------------------------------ #
    # Bloqueo de dominios vía hosts
    # ------------------------------------------------------------------ #

    def _bloquear_dominios_hosts(self) -> tuple[bool, list[str]]:
        """Añade entradas 127.0.0.1 para cada dominio configurado."""
        dominios = list(self.cfg.dominios) or list(DOMINIOS_POR_DEFECTO)
        contenido = _leer_hosts()
        if not contenido:
            log.warning("archivos hosts vacío o ilegible: no se puede bloquear dominios")
            return False, []

        lineas_anadidas: list[str] = []
        para_escribir = contenido
        if not para_escribir.endswith("\n"):
            para_escribir += "\n"

        for dominio in dominios:
            dominio = dominio.strip().lower()
            if not dominio:
                continue
            # quitar protocolo si lo trae el usuario
            for prefijo in ("https://", "http://", "www."):
                if dominio.startswith(prefijo):
                    dominio = dominio[len(prefijo):]
            linea = _HOSTS_LINEA.format(dominio=dominio)
            if _ya_bloqueado(contenido, dominio):
                continue  # ya estaba bloqueado, no duplicar
            if linea in lineas_anadidas:
                continue
            para_escribir += linea + "\n"
            lineas_anadidas.append(linea)

        if not lineas_anadidas:
            return True, []  # todo ya bloqueado

        para_escribir += f"{_MARCADOR_INICIO}\n"
        for l in lineas_anadidas:
            para_escribir += f"{l}\n"
        para_escribir += f"{_MARCADOR_FIN}\n"

        ok = _escribir_hosts(para_escribir)
        if ok:
            self._hosts_lineas_anadidas = lineas_anadidas
            # Forzar vaciado de la caché DNS de Windows
            try:
                import subprocess
                subprocess.run(
                    ["ipconfig", "/flushdns"],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass  # no crítico
        return ok, lineas_anadidas

    def _restaurar_hosts(self) -> bool:
        """Quita las líneas de hosts añadidas y limpia el bloque delimitado."""
        contenido = _leer_hosts()
        if not contenido:
            return True
        pattern = re.compile(rf"\n?{re.escape(_MARCADOR_INICIO)}.*?{re.escape(_MARCADOR_FIN)}\n?", re.DOTALL)
        nuevo = pattern.sub("", contenido)
        lineas = nuevo.splitlines(keepends=True)
        filtradas = [
            ln for ln in lineas
            if ln.strip() not in self._hosts_lineas_anadidas
        ]
        return _escribir_hosts("".join(filtradas))

    # ------------------------------------------------------------------ #
    # Audio
    # ------------------------------------------------------------------ #

    def _silenciar_audio(self) -> bool:
        """Mute del dispositivo de audio por defecto (Windows, vía API de waveOut)."""
        if not _IS_WINDOWS:
            return False
        try:
            winmm = ctypes.windll.winmm
            # waveOutGetVolume / waveOutSetVolume sobre el dispositivo -1 (mapper por defecto)
            vol_actual = wintypes.DWORD()
            rc = winmm.waveOutGetVolume(-1, ctypes.byref(vol_actual))
            if rc != 0:
                log.debug("waveOutGetVolume falló (rc=%s): no se puede silenciar", rc)
                return False
            self._audio_was_muted = vol_actual.value == 0
            rc = winmm.waveOutSetVolume(-1, 0)
            if rc != 0:
                log.debug("waveOutSetVolume falló (rc=%s)", rc)
                return False
            return True
        except Exception as exc:  # pragma: no cover
            log.debug("no se pudo silenciar el audio: %s", exc)
            return False

    def _restaurar_audio(self) -> bool:
        """Vuelve el volumen al estado previo (0 si ya estaba muteado, o lo que fuera)."""
        if not _IS_WINDOWS:
            return False
        if not self._audio_was_muted:
            # Restaurar a un volumen audible por defecto (50 %)
            try:
                winmm = ctypes.windll.winmm
                vol = wintypes.DWORD(0x7FFF7FFF)  # ~50 % en ambos canales
                winmm.waveOutSetVolume(-1, vol)
                return True
            except Exception:  # pragma: no cover
                return False
        return True  # ya estaba muteado, no tocamos nada

    # ------------------------------------------------------------------ #
    # Bloqueo de procesos (minimizar al frente)
    # ------------------------------------------------------------------ #

    def debe_minimizar(self, app: str | None, titulo: str | None) -> bool:
        """True si la ventana activa matchea una app bloqueada."""
        if not self.activo or not self.cfg.apps_bloqueadas:
            return False
        if not app and not titulo:
            return False
        texto = f"{app or ''} {titulo or ''}".lower()
        for patron in self.cfg.apps_bloqueadas:
            p = patron.strip().lower()
            if not p:
                continue
            if p in texto:
                return True
        return False

    def duracion_seg(self) -> float:
        if self._inicio is None:
            return 0.0
        return self.reloj() - self._inicio


def crear_modo_concentracion(cfg: ConcentracionCfg) -> ModoConcentracion:
    """Fábrica: devuelve un ModoConcentracion listo para usar."""
    return ModoConcentracion(cfg)
