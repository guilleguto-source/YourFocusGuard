"""Toast de Windows con winotify; degrada a banner de consola si no se puede."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)
_IS_WINDOWS = sys.platform == "win32"


def toast_disponible() -> bool:
    if not _IS_WINDOWS:
        return False
    try:
        import winotify  # noqa: F401
        return True
    except Exception:
        return False


def send_toast(titulo: str, mensaje: str, app_id: str = "YourFocusGuard") -> bool:
    """True si se mostró el toast nativo; False si hubo que degradar."""
    if not _IS_WINDOWS:
        log.info("toast (degradado a consola): %s | %s", titulo, mensaje)
        return False
    try:
        from winotify import Notification, audio

        aviso = Notification(
            app_id=app_id, title=titulo, msg=mensaje, duration="short"
        )
        aviso.set_audio(audio.Default, loop=False)
        aviso.show()
        return True
    except Exception as exc:
        log.warning("toast falló (%s); se muestra en consola", exc)
        return False
