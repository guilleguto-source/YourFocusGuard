"""Procesador de comandos externos (control.json) para YourFocusGuard (v0.8.2)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from colorama import Fore

from yourfocusguard.console_ui import linea_evento
from yourfocusguard.constants import TipoEvento

log = logging.getLogger(__name__)


class CommandProcessor:
    """Lee y despacha comandos declarados por la CLI o el panel en control.json."""

    def __init__(self, agente: Any) -> None:
        self.agente = agente

    def procesar(self, ahora: float) -> None:
        """Lee control.json y ejecuta el comando si está presente."""
        ruta: Path = self.agente.cfg.ruta_control
        if not ruta.is_file():
            return

        try:
            raw = ruta.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return

        if not isinstance(data, dict) or not data:
            return

        cmd = data.get("cmd")
        agente = self.agente

        if cmd in ("pause", "pause_manual"):
            minutos = float(data.get("minutos", agente.cfg.privacidad.pausa_rapida_min))
            agente.paused_until = ahora + minutos * 60
            agente._pausa_espera_confirmacion = bool(data.get("espera_confirmacion", False))
            agente._tick_en_pausa(ahora, "manual", detalle=f"{minutos:.0f} min (protegida)" if agente._pausa_espera_confirmacion else f"{minutos:.0f} min")
        elif cmd in ("resume", "resume_or_extend"):
            agente._pausa_espera_confirmacion = False
            if agente.paused_until is not None:
                agente.paused_until = None
                agente._reanudar(ahora, "manual")
            elif hasattr(agente, "guardia") and agente.guardia.activa and cmd == "resume_or_extend":
                minutos_extra = float(data.get("minutos", 15))
                if agente.guardia.fin is not None:
                    agente.guardia.fin += minutos_extra * 60
                agente.confirmar_sigo(ahora)
            else:
                agente.confirmar_sigo(ahora)
        elif cmd == "stop":
            agente._parar = True
        elif cmd == "task":
            agente.tarea = (data.get("texto") or "").strip()
            agente._evento(TipoEvento.TAREA, motivo=agente.tarea or "(borrada)")
            if agente.consola:
                linea_evento(f"tarea declarada: {agente.tarea or '(borrada)'}", Fore.CYAN)
        elif cmd == "session_start":
            agente._iniciar_sesion(ahora, data)
        elif cmd == "session_stop":
            if agente.guardia.activa:
                agente._terminar_sesion(ahora, "manual")
            elif agente.consola:
                linea_evento("no hay sesión activa que cerrar", Fore.YELLOW)
        elif cmd == "test_alert":
            agente.notifier.aviso("Prueba de aviso sutil (así se ve N1).")
            agente.notifier.toast(
                "YourFocusGuard · prueba de avisos",
                "Así se ve el toast (N2). Si lees esto en consola, winotify no está disponible.",
            )
            agente.notifier.voz("Hola, soy YourFocusGuard. Así suena el aviso de voz.")
            if agente.mascota is not None:
                agente.mascota.al_alerta(2, "prueba de avisos")
        elif cmd == "sigo":
            agente.confirmar_sigo(ahora)
        elif cmd == "privado":
            valor = bool(data.get("valor"))
            agente.cfg.modo_privado = valor
            agente._evento(
                TipoEvento.CEREBRO,
                motivo=f"modo_privado:{'on' if valor else 'off'}",
            )
            if agente.consola:
                linea_evento(
                    "modo privado ACTIVADO (solo Nivel B, cero nube)"
                    if valor
                    else "modo privado desactivado",
                    Fore.CYAN,
                )
        else:
            log.warning("comando de control desconocido: %r", cmd)

        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass
