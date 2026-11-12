"""Constantes y enumeraciones compartidas.

Los valores de estado, tipo, acción y motivo replican los contratos del
Apéndice B del blueprint (esquema SQLite + prompt v1), de modo que lo que
se registra en la base sea exactamente lo que el documento especifica.
"""
from __future__ import annotations

from enum import Enum


class Estado(str, Enum):
    """Estados de la máquina de atención (blueprint, cap. 5)."""

    EN_ESPERA = "EN_ESPERA"    # calentamiento / veredicto incierto
    FOCO = "FOCO"              # trabajando sin novedades
    PAUSA = "PAUSA"            # manual, pomodoro, privado o ausencia
    ESCALADA = "ESCALADA"      # desvío sostenido confirmado, escalera activa
    COOLDOWN = "COOLDOWN"      # silencio de 5 min tras la alerta de voz


class TipoEvento(str, Enum):
    """Tipos de fila en la tabla ``evento`` (Apéndice B + extensión sprint 1)."""

    INICIO = "inicio"
    FIN = "fin"
    DESVIO = "desvio"
    ALERTA = "alerta"
    PAUSA = "pausa"
    RETOMA = "retoma"
    DETECCION = "deteccion"    # latido por ciclo de análisis (calibración F5)
    REFUERZO = "refuerzo"      # micro-recompensa por foco continuo
    TAREA = "tarea"
    CEREBRO = "cerebro"        # degradaciones: fallback, disyuntor, presupuesto
    ERROR = "error"


class Accion(str, Enum):
    """Qué ejecutó realmente el orquestador (Apéndice B)."""

    NADA = "nada"
    MASCOTA = "mascota"
    AVISO = "aviso"
    TOAST = "toast"
    VOZ = "voz"


class Motivo(str, Enum):
    """Motivo del desvío, mismo vocabulario del prompt v1."""

    NINGUNO = "ninguno"
    REDES = "redes"
    VIDEO = "video"
    CELULAR = "celular"            # reservado para F3 (webcam)
    CONVERSACION = "conversacion"  # reservado para F3 (webcam)
    MIRADA = "mirada"              # reservado para F3 (webcam)
    OTRO = "otro"


#: Identificador de la versión del prompt en uso (Apéndice B: versionado desde el día 1).
PROMPT_ID_V1 = "v1"

#: Orígenes posibles de un veredicto.
ORIGEN_GEMINI = "nube:gemini"
ORIGEN_OPENAI = "nube:openai"
ORIGEN_HEURISTICA = "heuristica"
ORIGEN_CACHE = "cache"
ORIGEN_SESION = "sesion"   # modo sesión: reglas por predicados, sin imágenes

#: Cadencia del latido de detección registrado en la base (segundos).
HEARTBEAT_SEG = 60
