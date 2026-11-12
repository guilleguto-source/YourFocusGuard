"""Pre-graba los mensajes principales del asistente (caché de voz).

Esto responde a: "clonar una voz de algún tipo y grabar los principales
mensajes, al menos". En vez de clonar (pesado), pre-sintetizamos con la
voz neuronal TODAS las frases fijas del asistente. Resultado:

- Esos mensajes suenan al instante (0 ms de latencia, salen de caché)
- Funcionan incluso sin internet una vez cacheados
- La voz es siempre la misma, con personalidad consistente

v0.11-v0.12: se ampliaron las frases con memoria, briefing y
sincronización de calendario.

Uso (desde la raíz del proyecto):
    python precache_tts.py                    # perfil activo (config.json)
    python precache_tts.py --perfil salome_energica
    python precache_tts.py --todos            # los 6 perfiles (tarda más)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))

import tts  # noqa: E402

#: Catálogo de frases fijas del asistente (edítalo con las tuyas)
FRASES_FIJAS = [
    # Confirmaciones de tareas
    "Tarea guardada. ¡Vamos con todo!",
    "¡Excelente! Marqué la tarea como completada.",
    "No encontré una tarea pendiente con ese nombre.",
    "¡No tienes tareas pendientes por ahora! Todo al día.",
    # Calendario
    "¡Listo! Agendé tu evento en Google Calendar.",
    "No pude conectar con Google Calendar. Revisa la conexión.",
    # v0.10: sincronización bidireccional
    "Sincronización con Google Calendar lista.",
    "También liberé el hueco en tu Google Calendar.",
    # Alarmas
    "Alarma programada. Te aviso cuando se acabe el tiempo.",
    "¡Se acabó el tiempo! Terminaste tu bloque de enfoque.",
    "¡Se acabó el tiempo! Hora del descanso.",
    # v0.11: memoria
    "Nota guardada en tu memoria.",
    "No encontré notas con eso. Prueba con otras palabras.",
    "Encontré esto en tus notas.",
    # v0.11: briefing
    "Preparando tu resumen del día.",
    "Recuerda: hecho es mejor que perfecto. ¡Un paso a la vez!",
    # Audio
    "Reproduciendo tu música.",
    "Ruido marrón activado. Enfoque profundo.",
    "Ruido blanco activado.",
    "Audio detenido.",
    # Ánimo / acompañamiento TDAH
    "¡Aquí estoy contigo! ¿En qué nos enfocamos hoy?",
    "¡Vas muy bien! Sigue así.",
    "Un paso a la vez. Empecemos por lo más urgente.",
    "¡Buen trabajo! Tu futuro yo te lo agradece.",
    "Vamos a dividirlo en pasos pequeños. ¿Cuál es el primero?",
    "No te preocupes, retomemos donde lo dejaste.",
    # Errores
    "No te escuché bien. Intenta de nuevo, por favor.",
    "Ups, algo falló. Pero lo intentamos otra vez.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-graba frases fijas del asistente")
    parser.add_argument("--perfil", default=None, help="Perfil de voz (ver config.json)")
    parser.add_argument("--todos", action="store_true", help="Pre-grabar los 6 perfiles")
    args = parser.parse_args()

    perfiles = list(tts.PERFILES_VOZ.keys()) if args.todos else [args.perfil or tts.perfil_actual()]

    total_ok = 0
    total_err = 0
    for perfil_id in perfiles:
        nombre = tts.PERFILES_VOZ[perfil_id]["nombre"]
        print(f"\n=== Perfil: {nombre} ({perfil_id}) ===")
        for frase in FRASES_FIJAS:
            ruta = tts.sintetizar(frase, perfil=perfil_id)
            if ruta:
                print(f"  OK  {frase[:58]:60s}")
                total_ok += 1
            else:
                print(f"  ERR {frase[:58]:60s}  <- revisa internet / pip install edge-tts")
                total_err += 1

    print(f"\nListo: {total_ok} audios en caché, {total_err} errores.")
    print("Esos mensajes ahora suenan al instante y sin internet.")
    return 0 if total_err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
