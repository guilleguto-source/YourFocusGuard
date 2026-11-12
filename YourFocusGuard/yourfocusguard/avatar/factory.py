"""Fábrica del avatar: una sola decisión, un solo punto de cambio (v0.6.0).

``[avatar] proveedor`` decide la cara del asistente:

    auto      OpenPets si responde; si no, el avatar embed del panel, o la mascota tk
    embed     avatar embebido en el panel web local (sin OpenPets)
    openpets  solo OpenPets (sin fallback)
    tk        solo la mascota integrada tkinter
    ninguno   sin cara

El motor llama siempre a la misma interfaz (`iniciar`, `fijar_estado`,
`al_alerta`, `preguntar`, `respuestas`, `parar`), así que cambiar de cara no
toca ni una regla de vigilancia.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def crear_avatar(cfg):
    """Devuelve el avatar ya arrancado, o None si no hay cara disponible."""
    proveedor = str(getattr(cfg.avatar, "proveedor", "auto") or "auto").strip().lower()

    if proveedor == "ninguno":
        return None

    if proveedor == "embed":
        from yourfocusguard.avatar.embed import AvatarEmbed

        avatar = AvatarEmbed(cfg)
        if avatar.iniciar():
            return avatar
        return None

    if proveedor in ("auto", "openpets"):
        from yourfocusguard.avatar.openpets import AvatarOpenPets

        avatar = AvatarOpenPets(cfg)
        if avatar.iniciar():
            return avatar
        if proveedor == "openpets":
            log.warning(
                "avatar.proveedor=openpets pero OpenPets no responde: el "
                "asistente queda sin cara (revisa que esté abierto)"
            )
            return None
        log.info("OpenPets no está abierto: buscando avatar embebido o mascota integrada")

    if proveedor in ("auto", "tk") and getattr(cfg.mascota, "visible", True):
        from yourfocusguard.mascota import Mascota

        mascota = Mascota(cfg)
        mascota.iniciar()
        return mascota

    # Si tk no está visible pero el panel está activo, usar avatar embed
    if proveedor in ("auto", "embed") and getattr(cfg.panel, "activo", True):
        from yourfocusguard.avatar.embed import AvatarEmbed

        avatar = AvatarEmbed(cfg)
        if avatar.iniciar():
            return avatar

    return None
