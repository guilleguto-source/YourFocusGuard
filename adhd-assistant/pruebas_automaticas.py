"""Suite de pruebas automáticas del Asistente TDAH (v0.12).

Verifica TODO el sistema sin tocar tus datos reales:

1. Hace copia de seguridad de `data/tasks.json` y `data/memoria.json`
2. Levanta el servidor en un puerto de prueba (8799, sin Groq para
   resultados deterministas)
3. Ejecuta ~35 pruebas: módulos, registro de herramientas, router
   (reglas rápidas), memoria, timers, calendario sin credenciales y
   todos los endpoints HTTP (incluida la seguridad de origen)
4. Apaga el servidor y restaura tus datos

Uso (desde la raíz del proyecto):
    python pruebas_automaticas.py

Sale con código 0 si todo pasó (o fue omitido) y 1 si hay fallos.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
APP = RAIZ / "app"
sys.path.insert(0, str(APP))

PUERTO = 8799
BASE = f"http://localhost:{PUERTO}"

RESULTADOS = []  # (estado, numero, nombre, detalle)  estado: OK|FALLO|OMITIDO


def check(nombre: str, condicion: bool, detalle: str = "", omitir_si: bool = False):
    n = len(RESULTADOS) + 1
    if omitir_si:
        RESULTADOS.append(("OMITIDO", n, nombre, detalle))
    elif condicion:
        RESULTADOS.append(("OK", n, nombre, detalle))
    else:
        RESULTADOS.append(("FALLO", n, nombre, detalle))


def seccion(titulo: str):
    print(f"\n--- {titulo} ---")


# ---------------------------------------------------------------------------
# Cliente HTTP mínimo (sin dependencias externas)
# ---------------------------------------------------------------------------

def http(metodo: str, ruta: str, cuerpo: dict | None = None, origin: str | None = None):
    url = BASE + ruta
    data = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(url, data=data, method=metodo)
    req.add_header("Content-Type", "application/json")
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            cuerpo_resp = resp.read()
            try:
                return resp.status, json.loads(cuerpo_resp.decode("utf-8"))
            except Exception:
                return resp.status, {"_raw": cuerpo_resp}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"_error": str(e)}


def http_raw(metodo: str, ruta: str, origin: str | None = None):
    """Para respuestas binarias (MP3)."""
    req = urllib.request.Request(BASE + ruta, method=metodo)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, b"", ""
    except Exception as e:
        return 0, str(e).encode(), ""


# ---------------------------------------------------------------------------
# 1) Módulos: sintaxis + imports
# ---------------------------------------------------------------------------

def probar_modulos():
    seccion("1. Módulos (sintaxis e import)")
    esperados = [
        "server.py", "router.py", "main.py", "timer.py", "tasks_sync.py",
        "google_calendar.py", "audio_engine.py", "tts.py", "memoria.py",
        "herramientas.py", "utilidades.py",
    ]
    for mod in esperados:
        ruta = APP / mod
        existe = ruta.is_file()
        check(f"existe app/{mod}", existe)
        if existe:
            import py_compile
            try:
                py_compile.compile(str(ruta), doraise=True)
                check(f"sintaxis válida: {mod}", True)
            except Exception as e:
                check(f"sintaxis válida: {mod}", False, str(e)[:60])

    obsoletos = ["stt.py", "music.py", "config.py"]
    check(
        "sin código muerto (stt/music/config eliminados)",
        not any((APP / o).exists() for o in obsoletos),
        "ejecuta limpiar_residuos.py en tu proyecto viejo",
    )


# ---------------------------------------------------------------------------
# 2) Registro de herramientas (v0.12)
# ---------------------------------------------------------------------------

def probar_herramientas():
    seccion("2. Registro de herramientas (prep MCP)")
    import herramientas

    nombres = herramientas.nombres()
    check("12 herramientas registradas", len(nombres) == 12, f"hay {len(nombres)}")
    for esperada in ["crear_evento", "tarea_crear", "nota_crear", "briefing_diario", "audio_noise"]:
        check(f"registro incluye '{esperada}'", esperada in nombres)

    esquemas = herramientas.esquemas_mcp()
    valido = all(
        "name" in h and "description" in h
        and h.get("inputSchema", {}).get("type") == "object"
        for h in esquemas
    )
    check("esquemas MCP válidos (name/description/inputSchema)", valido)

    # JSON serializable (requisito para MCP)
    try:
        json.dumps(esquemas)
        check("esquemas serializables a JSON", True)
    except Exception:
        check("esquemas serializables a JSON", False)

    defs = herramientas.definiciones_para_llm()
    check(
        "definiciones LLM incluyen las 4 categorías",
        all(a in defs for a in ["crear_evento", "tarea_crear", "nota_crear", "charla"]),
    )

    v = herramientas.validar("crear_evento", {"summary": "x"})
    check("validar() detecta parámetro faltante", not v["ok"])
    v2 = herramientas.validar("crear_evento", {"summary": "x", "start_time": "y"})
    check("validar() acepta parámetros completos", v2["ok"])
    v3 = herramientas.validar("no_existe", {})
    check("validar() rechaza herramienta desconocida", not v3["ok"])


# ---------------------------------------------------------------------------
# 3) Utilidades (v0.10)
# ---------------------------------------------------------------------------

def probar_utilidades():
    seccion("3. Utilidades (fechas en español)")
    from utilidades import formatear_fecha_es, saludo_por_hora, normalizar_texto

    dt = datetime(2026, 11, 12, 15, 4)  # jueves
    check(
        "formatear_fecha_es",
        formatear_fecha_es(dt) == "jueves 12 de noviembre de 2026",
        formatear_fecha_es(dt),
    )
    check("saludo por hora (15h = tardes)", saludo_por_hora(dt) == "Buenas tardes")
    check("saludo por hora (7h = días)", saludo_por_hora(datetime(2026, 1, 1, 7, 0)) == "Buenos días")
    check("normalizar quita acentos", normalizar_texto("Café ÓrDen") == "cafe orden")


# ---------------------------------------------------------------------------
# 4) Router: reglas rápidas (0 ms, sin LLM)
# ---------------------------------------------------------------------------

def probar_router():
    seccion("4. Router — reglas rápidas (sin API)")
    import router as router_mod

    r = router_mod.Router()

    casos = [
        ("¿qué me toca hacer?", "tarea_listar"),
        ("ya terminé el informe de ventas", "tarea_completar"),
        ("mis pendientes", "tarea_listar"),
        ("pon ruido marrón", "audio_noise"),
        ("ruido blanco", "audio_noise"),
        ("ruido rosa para leer", "audio_noise"),
        ("pon música lofi hip hop", "audio_youtube"),
        ("para la música", "audio_stop"),
        ("resumen del día", "briefing_diario"),
        ("cómo va mi día", "briefing_diario"),
        ("busca en mis notas el wifi", "nota_buscar"),
    ]
    for frase, accion_esperada in casos:
        res = r.route(frase)
        check(
            f"'{frase}' -> {accion_esperada}",
            res.get("action") == accion_esperada,
            f"devolvió {res.get('action')}",
        )

    # Parseo de alarma compuesta
    res = r.route("pon alarma en 1 hora 5 minutos 30 segundos que diga sacar la ropa")
    ok = (
        res.get("action") == "crear_alarma"
        and res.get("seconds") == 3600 + 300 + 30
        and "ropa" in res.get("label", "")
    )
    check("alarma compuesta: 1h 5m 30s + etiqueta", ok, json.dumps(res, ensure_ascii=False)[:70])

    # Ruido correcto
    check(
        "ruido marrón -> noise_type brown",
        r.route("pon ruido marrón").get("noise_type") == "brown",
    )


# ---------------------------------------------------------------------------
# 5) Memoria (v0.11) — directo sobre el módulo
# ---------------------------------------------------------------------------

def probar_memoria():
    seccion("5. Memoria (notas + interacciones)")
    import memoria

    res = memoria.crear_nota("PRUEBA: el código de la PUERTA es 1234", fuente="voz")
    check("crear nota", res.get("status") == "ok")
    nota_id = (res.get("nota") or {}).get("id")

    lista = memoria.listar_notas()
    check("listar notas (aparece la nueva)", any(n["id"] == nota_id for n in lista))

    # Búsqueda tolerante a acentos/mayúsculas/stopwords
    encontradas = memoria.buscar_notas("¿qué anoté de la puerta?")
    check("buscar 'puerta' (tolerante a acentos)", len(encontradas) >= 1 and "1234" in encontradas[0]["texto"])

    encontradas2 = memoria.buscar_notas("codigo")
    check("buscar 'codigo' (sin acento encuentra 'código')", any("1234" in n["texto"] for n in encontradas2))

    check("buscar algo inexistente -> []", memoria.buscar_notas("zyxwvutsrqponmlk") == [])

    memoria.registrar_interaccion("prueba de memoria", "nota_crear", "Nota guardada")
    ctx = memoria.contexto_reciente_texto(5)
    check("contexto reciente registra la interacción", "prueba de memoria" in ctx)

    if nota_id:
        res_del = memoria.eliminar_nota(nota_id)
        check("eliminar nota", res_del.get("status") == "ok")
        check("nota ya no aparece", not any(n["id"] == nota_id for n in memoria.listar_notas()))


# ---------------------------------------------------------------------------
# 6) Timer directo (v0.10: fecha completa + announce)
# ---------------------------------------------------------------------------

def probar_timer_directo():
    seccion("6. Timer (fecha completa y anuncio)")
    from timer import TimerManager

    tm = TimerManager()
    res = tm.set_timer(1.0, "prueba unitaria")
    check("set_timer ok", res.get("status") == "ok")
    check("respuesta incluye fecha completa", "de noviembre" in res.get("message", "") or "de " in res.get("message", ""))

    time.sleep(1.6)
    vencidas = tm.pop_finished_unannounced()
    check("alarma vencida detectada", len(vencidas) == 1)
    if vencidas:
        check("mensaje_hablado con hora y fecha", "Son las" in vencidas[0].get("mensaje_hablado", ""), vencidas[0].get("mensaje_hablado", "")[:60])
    check("no repite el anuncio", tm.pop_finished_unannounced() == [])


# ---------------------------------------------------------------------------
# 7) Calendario sin credenciales (degradación elegante)
# ---------------------------------------------------------------------------

def probar_calendario():
    seccion("7. Calendario sin credenciales (no debe explotar)")
    from google_calendar import Calendar

    cal = Calendar()
    autenticado = cal.is_authenticated()
    res = cal.create_event("prueba", "2026-11-13T10:00:00-05:00")
    if autenticado:
        check("con credenciales: crea evento", res.get("status") == "ok")
        if res.get("id"):
            cal.eliminar_evento(res["id"])
    else:
        check("sin credenciales: error graceful (no excepción)", res.get("status") == "error")
        check("sin credenciales: listar -> []", cal.listar_eventos() == [])


# ---------------------------------------------------------------------------
# 8) HTTP: servidor completo
# ---------------------------------------------------------------------------

def probar_http(groq_activo: bool):
    seccion("8. Servidor HTTP (puerto de prueba)")

    # UI
    code, _ = http("GET", "/")
    check("GET / sirve la UI", code == 200, f"code={code}")

    # Salud
    code, s = http("GET", "/api/salud")
    check("GET /api/salud responde", code == 200)
    check("salud reporta versión 0.12.x", str(s.get("version", "")).startswith("0.12"), s.get("version", "?"))
    for campo in ["voz", "groq_configurado", "calendario_autenticado", "herramientas", "notas_guardadas"]:
        check(f"salud incluye '{campo}'", campo in s)

    # Herramientas
    code, h = http("GET", "/api/herramientas")
    check("GET /api/herramientas", code == 200 and len(h.get("herramientas", [])) == 12)

    # Tareas (crear + completar vía HTTP, se restaura después)
    code, t = http("POST", "/api/tasks", {"title": "PRUEBA AUTOMÁTICA: borrar luego", "priority": 3})
    check("POST /api/tasks crea tarea", code == 200 and t.get("status") == "ok")
    code, tasks = http("GET", "/api/tasks")
    check("GET /api/tasks la lista", any("PRUEBA AUTOMÁTICA" in str(x.get("title", "")) for x in tasks))
    code, comp = http("POST", "/api/tasks/complete", {"query": "PRUEBA AUTOMÁTICA"})
    check("POST /api/tasks/complete la completa", code == 200 and comp.get("status") == "ok")

    # Notas por HTTP
    code, n = http("POST", "/api/notas", {"texto": "PRUEBA HTTP: el wifi de casa es 9876"})
    check("POST /api/notas", code == 200 and n.get("status") == "ok")
    nota_id = (n.get("nota") or {}).get("id")
    code, ns = http("GET", "/api/notas?q=wifi")
    check("GET /api/notas?q=wifi la encuentra", any("9876" in str(x.get("texto", "")) for x in ns.get("notas", [])))
    code, nd = http("DELETE", f"/api/notas/{nota_id}")
    check("DELETE /api/notas/{id}", code == 200 and nd.get("status") == "ok")
    code, n400 = http("POST", "/api/notas", {"texto": ""})
    check("POST /api/notas vacía -> 400", code == 400, f"code={code}")

    # Briefing
    code, b = http("GET", "/api/briefing")
    check("GET /api/briefing", code == 200 and len(b.get("texto", "")) > 30)
    check("briefing contiene fecha en español", "de " in b.get("texto", "") and ("Buenos días" in b["texto"] or "Buenas tardes" in b["texto"] or "Buenas noches" in b["texto"]))

    # Chat: reglas rápidas por HTTP
    code, c = http("POST", "/api/chat", {"message": "¿qué me toca?"})
    check("chat 'qué me toca' -> tarea_listar", c.get("action") == "tarea_listar")
    code, c2 = http("POST", "/api/chat", {"message": "pon ruido marrón"})
    check("chat 'ruido marrón' -> audio_noise", c2.get("action") == "audio_noise" and c2.get("noise_type") == "brown")

    # Nota offline (solo determinista sin Groq)
    code, c3 = http("POST", "/api/chat", {"message": "anota que el código de prueba es 5555"})
    if groq_activo:
        check("chat 'anota que...' con LLM activo", c3.get("action") in ("nota_crear", "tarea_crear"), c3.get("action", "?"))
    else:
        check("chat 'anota que...' -> nota_crear (offline)", c3.get("action") == "nota_crear", c3.get("action", "?"))

    code, c4 = http("POST", "/api/chat", {"message": ""})
    check("chat mensaje vacío -> 400", code == 400)

    # Alarma end-to-end por HTTP
    code, a = http("POST", "/api/chat", {"message": "pon alarma en 2 segundos que diga prueba e2e"})
    check("chat crea alarma 2s", a.get("action") == "crear_alarma" and a.get("timer", {}).get("status") == "ok")
    time.sleep(3.2)
    code, an = http("GET", "/api/timers/announce")
    check("announce devuelve la alarma vencida", isinstance(an, list) and len(an) >= 1, f"code={code}")
    if isinstance(an, list) and an:
        check("announce incluye mensaje_hablado", "Son las" in an[0].get("mensaje_hablado", ""))
    code, an2 = http("GET", "/api/timers/announce")
    check("announce no repite", an2 == [])

    # TTS
    code, voces = http("GET", "/api/tts/voices")
    check("GET /api/tts/voices (6 perfiles)", code == 200 and len(voces.get("perfiles", {})) == 6)
    code, mp3, ctype = http_raw("GET", "/api/tts?text=Prueba%20de%20voz%20automtica")
    if code == 200:
        check("GET /api/tts devuelve MP3", ctype == "audio/mpeg" and len(mp3) > 1000, f"{len(mp3)} bytes")
    else:
        check("GET /api/tts devuelve MP3", False, f"code={code} (¿internet activo?)")
    code2, _, _ = http_raw("GET", "/api/tts")
    check("GET /api/tts sin text -> 400", code2 == 400)

    # Calendario endpoints (sin credenciales: deben responder sin explotar)
    code, ev = http("GET", "/api/calendario/eventos?dias=1")
    check("GET /api/calendario/eventos", code == 200 and ev.get("status") == "ok")
    code, sinc = http("POST", "/api/sync/calendario", {})
    check("POST /api/sync/calendario responde", code == 200 and sinc.get("status") == "ok")

    # Seguridad de origen
    code, _ = http("GET", "/api/tasks", origin="http://evil.com")
    check("Origin evil.com -> 403", code == 403)
    code, _ = http("GET", "/api/tasks", origin=f"http://localhost:{PUERTO}")
    check(f"Origin localhost:{PUERTO} -> 200", code == 200)

    # 404
    code, _ = http("GET", "/api/no-existe")
    check("ruta desconocida -> 404", code == 404)


# ---------------------------------------------------------------------------
# Orquestación: backup -> servidor -> pruebas -> restore
# ---------------------------------------------------------------------------

def backup_datos() -> Path | None:
    data = RAIZ / "data"
    if not data.exists():
        return None
    bak = RAIZ / "data" / "_backup_pruebas"
    if bak.exists():
        shutil.rmtree(bak)
    bak.mkdir(parents=True)
    for nombre in ["tasks.json", "memoria.json"]:
        origen = data / nombre
        if origen.exists():
            shutil.copy2(origen, bak / nombre)
    return bak


def restaurar_datos(bak: Path | None):
    data = RAIZ / "data"
    if bak is None:
        # no había datos: eliminar los generados por las pruebas
        for nombre in ["tasks.json", "memoria.json"]:
            f = data / nombre
            if f.exists():
                f.unlink()
        return
    for nombre in ["tasks.json", "memoria.json"]:
        origen = bak / nombre
        destino = data / nombre
        if origen.exists():
            shutil.copy2(origen, destino)
        elif destino.exists():
            destino.unlink()
    shutil.rmtree(bak, ignore_errors=True)


def esperar_servidor(segundos: float = 20.0) -> bool:
    inicio = time.time()
    while time.time() - inicio < segundos:
        code, _ = http("GET", "/api/salud")
        if code == 200:
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    print("=" * 62)
    print("🧪 PRUEBAS AUTOMÁTICAS — Asistente TDAH v0.12")
    print("=" * 62)
    print(f"Raíz del proyecto: {RAIZ}")
    print(f"Puerto de prueba:  {PUERTO} (tu servidor real en 8765 no se toca)")

    bak = backup_datos()

    # Pruebas directas (sin servidor)
    probar_modulos()
    probar_herramientas()
    probar_utilidades()
    probar_router()
    probar_memoria()
    probar_timer_directo()
    probar_calendario()

    # Servidor de prueba
    print(f"\n--- 8. Levantando servidor en :{PUERTO} ---")
    env = dict(os.environ)
    env["ASISTENTE_PUERTO"] = str(PUERTO)
    env["GROQ_API_KEY"] = ""       # determinista: reglas rápidas sin LLM
    env["VIKUNJA_TOKEN"] = ""      # modo local, sin tocar tu Vikunja real
    proc = subprocess.Popen(
        [sys.executable, str(APP / "server.py")],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(RAIZ),
    )
    try:
        if not esperar_servidor():
            check("servidor de prueba levanta", False, "no respondió /api/salud en 20s")
        else:
            check("servidor de prueba levanta", True)
            code, s = http("GET", "/api/salud")
            groq_activo = bool(s.get("groq_configurado"))
            if groq_activo:
                print("   (nota: Groq quedó activo por tu .env; pruebas LLM se relajan)")
            probar_http(groq_activo)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        restaurar_datos(bak)
        print("\n(data restaurada: tus tareas y notas reales quedaron intactas)")

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------
    print("\n" + "=" * 62)
    ok = sum(1 for e in RESULTADOS if e[0] == "OK")
    fallos = [r for r in RESULTADOS if r[0] == "FALLO"]
    omitidos = sum(1 for e in RESULTADOS if e[0] == "OMITIDO")

    for estado, n, nombre, detalle in RESULTADOS:
        icono = {"OK": "✅", "FALLO": "❌", "OMITIDO": "⏭️ "}[estado]
        extra = f"  [{detalle}]" if detalle and estado != "OK" else ""
        print(f"{icono} {n:02d} {nombre}{extra}")

    print("-" * 62)
    print(f"RESULTADO: {ok} OK · {len(fallos)} FALLOS · {omitidos} omitidos / {len(RESULTADOS)} pruebas")
    if fallos:
        print("\n❌ Hay fallos: revisa las líneas de arriba antes de pasar a la fase MCP.")
        return 1
    print("\n✅ Todo verde: el asistente está listo. Siguiente parada: MCP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
