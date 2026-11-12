import os
import sys

# Asegurar que app esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from router import Router
from google_calendar import Calendar
from music import Music


def main():
    print("\n" + "=" * 55)
    print("🧠 ASISTENTE TDAH: INICIADO")
    print("• Google Calendar: Conexión activa")
    print("• Extracción inteligente de fechas y eventos: Activada")
    print("=" * 55)
    print("Escribe tu instrucción o deja vacío para salir.\n")

    router = Router()
    calendar = Calendar()
    music = Music()

    while True:
        try:
            user_input = input("Tú: ").strip()
            if not user_input or user_input.lower() in ("salir", "exit", "quit"):
                break

            result = router.route(user_input)
            action = result.get("action")

            if action == "crear_evento":
                ev = result.get("event_data", {})
                print(f"\n⏳ Agendando en tu Google Calendar...")
                print(f"   Título: {ev.get('summary')}")
                print(f"   Inicio: {ev.get('start_time')}")
                if ev.get("location"):
                    print(f"   Lugar:  {ev.get('location')}")

                res = calendar.create_event(
                    summary=ev.get("summary", "Evento TDAH"),
                    start_time=ev.get("start_time"),
                    end_time=ev.get("end_time"),
                    description=ev.get("description", ""),
                    location=ev.get("location", ""),
                )

                if res.get("status") == "ok":
                    print(f"✅ Asistente: {res.get('message')}")
                    if res.get("htmlLink"):
                        print(f"🔗 Ver evento: {res.get('htmlLink')}\n")
                else:
                    print(f"❌ Error al agendar: {res.get('message')}\n")

            elif action == "reproducir_musica":
                track = result.get("track_name", user_input)
                res = music.play_track(track_name=track)
                print(f"🎵 Asistente: {res.get('message')}\n")

            else:
                resp = result.get("response", "¡Aquí estoy contigo!")
                print(f"💬 Asistente: {resp}\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"⚠️ Error: {e}\n")

    print("\n👋 Asistente detenido.")


if __name__ == "__main__":
    main()
