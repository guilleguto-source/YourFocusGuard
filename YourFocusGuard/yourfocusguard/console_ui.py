"""Salida de consola coloreada (CLI del sprint 1; la mascota llega en F4)."""
from __future__ import annotations

import time

from colorama import Fore, Style

from yourfocusguard import __version__
from yourfocusguard.constants import Estado

COLORES = {
    Estado.EN_ESPERA: Fore.LIGHTBLACK_EX,
    Estado.FOCO: Fore.GREEN,
    Estado.PAUSA: Fore.CYAN,
    Estado.ESCALADA: Fore.RED,
    Estado.COOLDOWN: Fore.YELLOW,
}


def estado_coloreado(estado: Estado, ancho: int = 10) -> str:
    color = COLORES.get(estado, "")
    return f"{color}{estado.value:<{ancho}}{Style.RESET_ALL}"


def linea_ciclo(
    ts: float,
    estado: Estado,
    app: str | None,
    titulo: str | None,
    origen: str,
    confianza: float,
    idle: float | None = None,
) -> None:
    """Línea de estado que se imprime en cada captura."""
    hora = time.strftime("%H:%M:%S", time.localtime(ts))
    ventana = (titulo or "")[:46]
    app_txt = (app or "?")[:18]
    idle_txt = f" · idle {idle:.0f}s" if idle is not None else ""
    print(
        f"{Fore.LIGHTBLACK_EX}{hora}{Style.RESET_ALL}  "
        f"{estado_coloreado(estado)} "
        f"{app_txt:<18} {ventana:<46} "
        f"{Fore.LIGHTBLACK_EX}{origen} {confianza:.2f}{idle_txt}{Style.RESET_ALL}"
    )


def linea_evento(mensaje: str, color: str = "") -> None:
    print(f"  {color}>> {mensaje}{Style.RESET_ALL}")


def banner_inicio(
    perfil: str,
    maquina: str,
    cerebro: str,
    tarea: str,
    atajo: str,
    intervalo: int,
) -> None:
    ancho = 58

    def fila(texto: str) -> str:
        return f"{Fore.CYAN}║{Style.RESET_ALL}  {texto:<{ancho - 4}}{Fore.CYAN}║{Style.RESET_ALL}"

    print()
    print(f"{Fore.CYAN}╔{'═' * ancho}╗{Style.RESET_ALL}")
    print(fila(f"YourFocusGuard v{__version__} — agente de foco (TDAH)"))
    print(f"{Fore.CYAN}╠{'═' * ancho}╣{Style.RESET_ALL}")
    print(fila(f"perfil: {perfil} · máquina: {maquina}"))
    print(fila(f"cerebro: {cerebro}"[: ancho - 2]))
    tarea_txt = tarea or '(sin declarar — usa: python run.py task "...")'
    print(fila(f"tarea: {tarea_txt}"[: ancho - 2]))
    print(fila(f"captura cada {intervalo} s · pausa rápida: {atajo}"))
    print(f"{Fore.CYAN}╚{'═' * ancho}╝{Style.RESET_ALL}")
    print(f"{Fore.LIGHTBLACK_EX}  Ctrl+C detiene el agente · los eventos quedan en SQLite{Style.RESET_ALL}")
    print()
