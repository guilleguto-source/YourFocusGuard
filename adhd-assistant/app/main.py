import os
import sys

# Asegurar que app esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

from router import Router
from google_calendar import Calendar
from tasks_sync import TasksSyncManager
from timer import TimerManager
from audio_engine import AudioEngine
import memoria
import herramientas


def main():
    print("\n" + "=" * 55)
    print("🧠 ASISTENTE TDAH: INICIADO (CLI)")
    print("• Google Calendar: Conexión activa")
    print("• Memoria: notas + contexto de conversación")
    print(f"• Herramientas registradas: {len(herramientas.nombres())}")
    print("=" * 55)
    print("Escribe tu instrucción o deja vacío para salir.")
    print("Pruébame: 'resumen del día' · 'anota que el wifi es 1234'")
    print("          'qué anoté del wifi' · 'alarma en 5 min'")
    print()

    router = Router()
    calendar = Calendar()
    tasks_mgr = TasksSyncManager()
    timer_mgr = TimerManager()
    audio_engine = AudioEngine()

    while True:
        try:
            user_input = input("Tú: ").strip()
            if not user_input or user_input.lower() in ("salir", "exit", "quit"):
                break

            result = router.route(user_input)
            action = result.get("action")

            if action == "crear_evento":
                print(f"\n⏳ Agendando en tu Google Calendar...")
                print(f"   Título: {result.get('summary')}")
                print(f"   Inicio: {result.get('start_time')}")

                res = calendar.create_event(
                    summary=result.get("summary", "Evento TDAH"),
                    start_time=result.get("start_time"),
                    end_time=result.get("end_time"),
                    description=result.get("description", ""),
                    location=result.get("location", ""),
                )

                if res.get("status") == "ok":
                    print(f"✅ Asistente: {res.get('message')}")
                    if res.get("htmlLink"):
                        print(f"🔗 Ver evento: {res.get('htmlLink')}\n")
                else:
                    print(f"❌ Error al agendar: {res.get('message')}\n")

            elif action == "tarea_crear":
                res = tasks_mgr.add_task(
                    title=result.get("title", user_input),
                    priority=result.get("priority", 2),
                    due_date=result.get("due_date"),
                )
                print(f"📝 Asistente: {res.get('message')}\n")

            elif action == "tarea_listar":
                tasks = tasks_mgr.list_tasks(filter_done=False)
                if tasks:
                    print("📋 Asistente: Tienes estos pendientes:")
                    for t in tasks[:5]:
                        print(f"   • {t['title']}")
                else:
                    print("📋 Asistente: ¡No tienes tareas pendientes por ahora!\n")

            elif action == "tarea_completar":
                res = tasks_mgr.complete_task(result.get("query", user_input))
                print(f"✅ Asistente: {res.get('message')}\n")

            elif action == "crear_alarma":
                res = timer_mgr.set_timer(
                    duration_seconds=result.get("seconds", 600),
                    label=result.get("label", "Recordatorio"),
                )
                print(f"⏰ Asistente: {res.get('message')}\n")

            elif action == "nota_crear":
                res = memoria.crear_nota(result.get("texto", user_input), fuente="voz")
                print(f"🧠 Asistente: {res.get('message')}\n")

            elif action == "nota_buscar":
                encontradas = memoria.buscar_notas(result.get("query", user_input))
                if encontradas:
                    print(f"🧠 Asistente: Encontré {len(encontradas)} nota(s):")
                    for n in encontradas[:5]:
                        print(f"   • {n['texto']}")
                else:
                    print("🧠 Asistente: No encontré notas con eso.\n")

            elif action == "briefing_diario":
                res = memoria.briefing_diario(calendar, tasks_mgr)
                print(f"\n☀️  Asistente: {res.get('texto')}\n")

            elif action == "audio_youtube":
                print(f"🎵 El streaming de YouTube está disponible en el panel web:")
                print(f"   http://localhost:8765 (busca '{result.get('query')}') ahí)\n")

            elif action == "audio_noise":
                print(f"🎧 El generador de ruido ({result.get('noise_type')}) está disponible en el panel web.\n")

            else:
                resp = result.get("response", "¡Aquí estoy contigo!")
                print(f"💬 Asistente: {resp}\n")

            # Registrar en memoria de conversación
            memoria.registrar_interaccion(user_input, action or "charla")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"⚠️ Error: {e}\n")

    print("\n👋 Asistente detenido.")


if __name__ == "__main__":
    main()
