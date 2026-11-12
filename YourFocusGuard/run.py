#!/usr/bin/env python3
"""CLI de YourFocusGuard.

    python run.py start            arranca el agente (Ctrl+C para detener)
                                   (con panel web: http://127.0.0.1:8756)
    python run.py start --sin-panel  arranca sin el panel web
    python run.py panel            solo el Panel del Guardián (sin agente)
    python run.py mascota [--demo]  la guardiana en el escritorio (pruébala)
    python run.py pause [min]      pausa rápida (15 min por defecto)
    python run.py resume           reanuda
    python run.py sigo             "sigo en la tarea": cierra el aviso actual
    python run.py stop             detiene el agente limpiamente
    python run.py status           estado y resumen del día
    python run.py task "texto"     declara la tarea de la sesión
    python run.py session start "editar fotos" --apps photoshop,lightroom
                                   guardián de tarea: sin capturas mientras
                                   cumples; avisa si te alejas o te congelas
    python run.py session stop     cierra la sesión con resumen
    python run.py session status   cómo va la sesión activa
    python run.py inspect [seg]    muestra la ventana activa (para armar listas)
    python run.py test-alert [n]   prueba la escalera de alertas 1..n
    python run.py test-cam         toma UNA foto con la webcam y la guarda
    python run.py doctor           diagnóstico de instalación
    python run.py export           exporta eventos a CSV
    python run.py purge --si       borra todos los eventos

Todo comando funciona mientras el agente corre en otra consola: se
comunican por un archivo de control que el motor lee en cada ciclo.
"""
from __future__ import annotations

import os
import sys

# Forzar codificación UTF-8 en Windows para consola y subprocess
if sys.platform == "win32":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import colorama
from dotenv import load_dotenv

# Cargar .env del proyecto (claves de API) antes de construir cerebros.
load_dotenv(Path(__file__).resolve().parent / ".env")

colorama.init()

from yourfocusguard import __version__  # noqa: E402
from yourfocusguard.actions.notifier import Notifier  # noqa: E402
from yourfocusguard.actions.toast import toast_disponible  # noqa: E402
from yourfocusguard.actions.tts import voces_disponibles  # noqa: E402
from yourfocusguard.brain.gemini_brain import GeminiBrain  # noqa: E402
from yourfocusguard.brain.heuristic import HeuristicBrain  # noqa: E402
from yourfocusguard.brain.openai_brain import OpenAIBrain  # noqa: E402
from yourfocusguard.brain.router import BrainRouter  # noqa: E402
from yourfocusguard.capture import window_info  # noqa: E402
from yourfocusguard.capture.camera import CamaraWeb  # noqa: E402
from yourfocusguard.capture.screen import grab_screen_jpeg  # noqa: E402
from yourfocusguard.capture.window_info import get_active_window, is_fullscreen  # noqa: E402
from yourfocusguard.config import load_config  # noqa: E402
from yourfocusguard.constants import Estado  # noqa: E402
from yourfocusguard.engine import Agent  # noqa: E402
from yourfocusguard.logging_setup import setup_logging  # noqa: E402
from yourfocusguard.mascota import Mascota  # noqa: E402
from yourfocusguard.memory.models import FrameSnapshot  # noqa: E402
from yourfocusguard.panel import PanelServidor  # noqa: E402
from yourfocusguard.privacy.exclusions import Exclusiones  # noqa: E402
from yourfocusguard.storage.db import EventDB  # noqa: E402
from yourfocusguard.actions.concentracion import crear_modo_concentracion  # noqa: E402
from yourfocusguard.capture.presencia import crear_detector_presencia  # noqa: E402
from yourfocusguard.avatar.focus_bridge import crear_focus_bridge  # noqa: E402


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def _color_estado(estado: str) -> str:
    from colorama import Fore, Style

    colores = {
        "FOCO": Fore.GREEN, "ESCALADA": Fore.RED, "COOLDOWN": Fore.YELLOW,
        "PAUSA": Fore.CYAN, "EN_ESPERA": Fore.LIGHTBLACK_EX,
        "DETENIDO": Fore.LIGHTBLACK_EX,
    }
    return f"{colores.get(estado, '')}{estado}{Style.RESET_ALL}"


def _escribir_control(cfg, datos: dict) -> None:
    # Intentar enviar vía API REST si el panel está activo
    puerto = getattr(cfg.panel, "puerto", 8756)
    url = f"http://127.0.0.1:{puerto}/api/control"
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            data=json.dumps(datos, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                return
    except Exception:
        # Fallback a control.json si el panel no responde o no está levantado
        pass

    ruta = cfg.ruta_control
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta)



def _leer_estado(cfg) -> dict | None:
    try:
        return json.loads(cfg.ruta_estado.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _agente_vivo(cfg, estado: dict | None) -> bool:
    if not estado or estado.get("estado") == "DETENIDO":
        return False
    try:
        actualizado = datetime.fromisoformat(estado["actualizado"])
        return (datetime.now().astimezone() - actualizado).total_seconds() < 120
    except (KeyError, ValueError):
        return False


def _construir_nube(cfg, log):
    """Cerebro A según configuración; None (con aviso) si no se puede usar."""
    proveedor = cfg.cerebro.proveedor_nube
    if cfg.modo_privado or proveedor == "ninguno":
        return None
    if proveedor == "gemini":
        if not os.environ.get("GEMINI_API_KEY", "").strip():
            log.warning("proveedor gemini sin GEMINI_API_KEY: solo Nivel B hoy")
            return None
        return GeminiBrain(cfg)
    if proveedor == "openai":
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            log.warning("proveedor openai sin OPENAI_API_KEY: solo Nivel B hoy")
            return None
        return OpenAIBrain(cfg)
    log.warning("proveedor desconocido %r: solo Nivel B", proveedor)
    return None


# --------------------------------------------------------------------------- #
# Comandos
# --------------------------------------------------------------------------- #

def _ejecutar_agente_con_servicios(cfg, args, log) -> int:
    """Arranca panel, base de datos, router y bucle del agente."""
    panel = None
    if cfg.panel.activo and not getattr(args, "sin_panel", False):
        panel = PanelServidor(cfg)
        if panel.arrancar(abrir_navegador=cfg.panel.abrir_navegador):
            print(f"  Panel del Guardián: {panel.url}  (ajustes en vivo; Ctrl+C detiene todo)")
            print()
            if getattr(cfg.avatar, "proveedor", "") in ("embed", "auto"):
                try:
                    from yourfocusguard.desktop_pet import lanzar_mascota_escritorio
                    mascota_id = getattr(cfg.avatar, "mascota", "null-wisp")
                    lanzar_mascota_escritorio(cfg.panel.puerto, mascota=mascota_id)
                    cfg.mascota.visible = False
                except Exception as exc:
                    log.warning("No se pudo lanzar mascota flotante: %s", exc)
        else:
            panel = None

    db = EventDB(cfg.ruta_db)
    cloud = _construir_nube(cfg, log)
    router = BrainRouter(cfg, local=HeuristicBrain(cfg), cloud=cloud, presupuesto=db)

    concentracion = crear_modo_concentracion(cfg.concentracion)
    presencia = crear_detector_presencia(cfg.presencia)
    focus_bridge = crear_focus_bridge(cfg, None)
    agente = Agent(
        cfg, db, router,
        concentracion_fn=concentracion,
        presencia_fn=presencia,
        focus_bridge=focus_bridge,
    )
    try:
        agente.run()
    finally:
        if panel is not None:
            panel.parar()
    return 0


def cmd_start(args) -> int:
    cfg = load_config(perfil=args.profile, modo_privado=args.privado)
    nivel = "DEBUG" if args.verbose else cfg.registro.nivel
    setup_logging(nivel, cfg.ruta_log)
    log = logging.getLogger("yourfocusguard.start")
    return _ejecutar_agente_con_servicios(cfg, args, log)


def cmd_panel(args) -> int:
    """Panel del Guardián sin agente: configura y cierra cuando quieras."""
    cfg = load_config(perfil=args.profile)
    if args.puerto:
        cfg.panel.puerto = args.puerto
    setup_logging(cfg.registro.nivel, cfg.ruta_log)
    panel = PanelServidor(cfg)
    if not panel.arrancar(abrir_navegador=not args.sin_abrir):
        print()
        print(f"  No se pudo abrir el puerto {cfg.panel.puerto}.")
        print("  ¿Hay otro panel corriendo? Ciérralo o usa --puerto 8757.")
        print()
        return 1
    print()
    print(f"  Panel del Guardián: {panel.url}")
    print("  Ajustes, prohibiciones y modos de aviso; los cambios van a config/user.toml.")
    print("  Ctrl+C para cerrar el panel.")
    print()
    try:
        panel.servir_para_siempre()
    except KeyboardInterrupt:
        pass
    print("  Panel cerrado.")
    return 0


def cmd_mascota(args) -> int:
    """La guardiana de escritorio, suelta o en modo demo."""
    cfg = load_config(perfil=args.profile)
    if args.tema:
        cfg.mascota.tema = args.tema
    cfg.mascota.visible = True
    setup_logging(cfg.registro.nivel, cfg.ruta_log)
    m = Mascota(cfg)
    m.iniciar()
    if not m.disponible:
        print()
        print("  La mascota necesita Windows con escritorio (tkinter viene con Python).")
        print("  En este entorno no hay pantalla: el agente la activará en tu PC.")
        print()
        return 1
    print()
    print(f"  Guardiana en pantalla (tema {cfg.mascota.tema}).")
    if args.demo:
        print("  Demo: cicla sus estados cada 3 s (Ctrl+C para salir).")
        secuencia = [
            ("FOCO", ""), ("ESCALADA", "redes"), ("PAUSA", ""),
            ("COOLDOWN", ""), ("EN_ESPERA", ""),
        ]
        try:
            while True:
                for est, det in secuencia:
                    m.fijar_estado(est, det)
                    if est == "ESCALADA":
                        m.al_alerta(2, "prueba de la burbuja")
                    time.sleep(3)
        except KeyboardInterrupt:
            pass
    else:
        m.fijar_estado("EN_ESPERA", "esperando al agente")
        print("  Un clic abre el panel; se arrastra. Ctrl+C para salir.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    m.parar()
    print()
    return 0


def cmd_pause(args) -> int:
    cfg = load_config(perfil=args.profile)
    minutos = args.minutos
    _escribir_control(cfg, {"cmd": "pause", "minutos": minutos})
    vivo = _agente_vivo(cfg, _leer_estado(cfg))
    nota = "" if vivo else "  (aviso: el agente no parece estar corriendo; se aplicará al arrancar)"
    print(f"Pausa de {minutos} min enviada.{nota}")
    return 0


def cmd_resume(args) -> int:
    cfg = load_config(perfil=args.profile)
    _escribir_control(cfg, {"cmd": "resume"})
    print("Reanudación enviada al agente.")
    return 0


def cmd_sigo(args) -> int:
    """v0.5.0: respuesta "sigo en la tarea" (cierra el aviso, sin pausar)."""
    cfg = load_config(perfil=args.profile)
    _escribir_control(cfg, {"cmd": "sigo"})
    print("Confirmado: sigo en la tarea (el aviso se cierra en el próximo ciclo).")
    print("En el escritorio tienes el mismo gesto con Ctrl+Alt+F11.")
    return 0


def cmd_stop(args) -> int:
    cfg = load_config(perfil=args.profile)
    _escribir_control(cfg, {"cmd": "stop"})
    print("Orden de detención enviada (el agente cierra en el próximo ciclo).")
    return 0


def cmd_task(args) -> int:
    cfg = load_config(perfil=args.profile)
    if args.texto is None:
        estado = _leer_estado(cfg)
        tarea = (estado or {}).get("tarea") or "(sin tarea declarada)"
        print(f"Tarea actual: {tarea}")
        return 0
    _escribir_control(cfg, {"cmd": "task", "texto": args.texto})
    print(f"Tarea declarada: {args.texto!r} (llega al agente en el próximo ciclo)")
    return 0


def cmd_session_start(args) -> int:
    cfg = load_config(perfil=args.profile)
    apps = [a.strip() for a in (args.apps or "").split(",") if a.strip()]
    aux = [a.strip() for a in (args.aux or "").split(",") if a.strip()]

    # v0.5.0: detectar las apps que estás usando antes de declarar la sesión.
    if args.detectar and not apps:
        segundos = float(args.detectar)
        print()
        print(f"  Detectando apps durante {segundos:.0f} s…")
        print("  Cambia a tu programa de trabajo (Lightroom, Photoshop, el editor).")
        muestras = window_info.apps_mas_usadas(
            segundos, 1.0, cfg.heuristica.apps_neutras, gracia=2.0
        )
        total = sum(n for _, n in muestras) or 1
        apps = [app for app, n in muestras if n / total >= 0.10][:5]
        if apps:
            print(f"  Detectadas: {', '.join(apps)}")
        else:
            print("  No se detectó ninguna app de trabajo: la sesión solo vigilará inactividad.")

    _escribir_control(
        cfg,
        {
            "cmd": "session_start",
            "texto": args.texto,
            "apps": apps,
            "apps_aux": aux,
            "minutos": args.min,
        },
    )
    vivo = _agente_vivo(cfg, _leer_estado(cfg))
    nota = "" if vivo else "  (aviso: el agente no parece estar corriendo; se aplicará al arrancar)"
    print()
    print(f"  Sesión declarada: {args.texto!r}{nota}")
    print(f"    apps objetivo: {', '.join(apps) if apps else '(ninguna: solo regla de inactividad)'}")
    if aux:
        print(f"    toleradas:     {', '.join(aux)}")
    print(
        f"    reglas:        alerta si {cfg.sesion.segundos_fuera_app} s fuera de las apps "
        f"o {cfg.sesion.segundos_inactivo} s sin tocar nada"
    )
    if cfg.camara.habilitada and cfg.sesion.verificar_con_camara_seg > 0:
        print(
            f"    cámara:        foto de verificación tras "
            f"{cfg.sesion.verificar_con_camara_seg} s sin input"
        )
    print("    mientras cumplas: cero capturas, cero nube.")
    print()
    return 0


def cmd_session_stop(args) -> int:
    cfg = load_config(perfil=args.profile)
    _escribir_control(cfg, {"cmd": "session_stop"})
    print("Cierre de sesión enviado (el agente muestra el resumen en el próximo ciclo).")
    return 0


def cmd_session_status(args) -> int:
    cfg = load_config(perfil=args.profile)
    estado = _leer_estado(cfg) or {}
    ses = estado.get("sesion") or {}
    print()
    if not ses.get("activa"):
        print("  Sin sesión activa. Para activarla:")
        print('    python run.py session start "editar fotos de la boda" --apps photoshop,lightroom')
        print()
        return 0
    print(f"  Sesión activa · tarea: {estado.get('tarea') or '(sin nombre)'}")
    print("  " + "-" * 58)
    apps = ses.get("apps") or []
    print(f"  apps objetivo:   {', '.join(apps) if apps else '(ninguna: solo regla de inactividad)'}")
    fuera = ses.get("fuera_hace_s")
    if fuera is not None:
        print(f"  en la tarea:     visto por última vez hace {fuera} s")
    idle = ses.get("idle_s")
    if idle is not None:
        print(f"  input:           último hace {idle} s")
    print(f"  alertas hoy:     {ses.get('disparos', 0)} disparos de la escalera")
    if ses.get("fin"):
        print(f"  cierre auto:     {ses['fin']}")
    print()
    return 0


def cmd_status(args) -> int:
    cfg = load_config(perfil=args.profile)
    estado = _leer_estado(cfg)
    vivo = _agente_vivo(cfg, estado)

    print()
    print(f"  YourFocusGuard v{__version__} · perfil {cfg.agente.perfil} · {cfg.agente.maquina}")
    print("  " + "-" * 58)
    if estado:
        e = estado.get("estado", "?")
        print(f"  Estado:          {_color_estado(e)}  ({'corriendo' if vivo else 'sin señal reciente'})")
        if estado.get("tarea"):
            print(f"  Tarea:           {estado['tarea']}")
        if estado.get("cerebro"):
            print(f"  Último cerebro:  {estado['cerebro']}")
        if estado.get("modo_privado"):
            print("  Modo privado:    SÍ (solo heurística local)")
        pausa = estado.get("pausa") or {}
        if pausa.get("motivo"):
            print(f"  En pausa:        {pausa['motivo']} (hasta {pausa.get('hasta', '?')})")
        pom = estado.get("pomodoro") or {}
        if pom.get("fase"):
            print(
                f"  Pomodoro:        fase {pom['fase']} · ciclo {pom.get('ciclos', 0)} "
                f"· foco acumulado {pom.get('foco_acumulado_min', 0)} min"
            )
        print(f"  Actualizado:     {estado.get('actualizado')}")
    else:
        print("  Estado:          (el agente no ha corrido todavía en esta carpeta de datos)")

    if cfg.ruta_db.exists():
        db = EventDB(cfg.ruta_db)
        resumen = db.resumen_hoy()
        recientes = db.eventos_recientes(6)
        presupuesto = db.presupuesto_hoy()
        db.cerrar()

        print("  " + "-" * 58)
        print("  Hoy:")
        minutos = resumen["minutos_estado"]
        if minutos:
            partes = ", ".join(f"{v} min {k}" for k, v in sorted(minutos.items()))
            print(f"    Tiempo por estado: {partes}")
        print(
            f"    Desvíos: {resumen['desvios']} · retomas: {resumen['retomas']} · "
            f"eventos: {resumen['eventos_total']}"
        )
        if resumen["alertas"]:
            alertas = ", ".join(f"{v}x {k}" for k, v in sorted(resumen["alertas"].items()))
            print(f"    Alertas: {alertas}")
        print(f"    Nube gastada hoy (estimado): {presupuesto:.3f} USD de {cfg.cerebro.presupuesto_diario_usd} USD")

        usados = db.presupuestos_hoy()
        if usados:
            print("    Prohibiciones (primer plano hoy):")
            for entrada in cfg.prohibiciones.lista:
                usado = usados.get(entrada.patron, 0)
                pct = 100 * usado / max(1, entrada.limite_min_dia * 60)
                estado = "AGOTADO" if pct >= 100 else f"{pct:.0f}%"
                print(
                    f"      {entrada.patron}: {usado // 60} de {entrada.limite_min_dia} min "
                    f"({estado})" + (" · bloqueo activo" if entrada.bloqueo_activo else "")
                )

        if recientes:
            print("  " + "-" * 58)
            print("  Últimos eventos:")
            for fila in recientes:
                hora = (fila["ts"] or "")[11:19]
                detalle = fila["motivo"] or ""
                print(
                    f"    {hora}  {fila['estado']:<9} {fila['tipo']:<9} "
                    f"{fila['accion'] or '':<7} {str(detalle)[:34]}"
                )
    print()
    return 0


def cmd_inspect(args) -> int:
    cfg = load_config(perfil=args.profile)
    exclusiones = Exclusiones(cfg.privacidad.apps_excluidas, cfg.privacidad.titulos_excluidos)
    cerebro = HeuristicBrain(cfg)
    print()
    print("  Ventana activa cada 2 s (Ctrl+C para cortar).")
    print("  Usa lo que ves para completar tus listas en config/user.toml:")
    print("  apps_enfoque / apps_distraccion / apps_neutras / titulos_distraccion.")
    print()
    fin = time.time() + args.segundos
    try:
        while time.time() < fin:
            app, titulo = get_active_window()
            snap = FrameSnapshot(ts=time.time(), app=app, title=titulo)
            clase = cerebro.classify(snap)
            excl = exclusiones.excluida(app, titulo)
            extra = ""
            if excl:
                extra = f"  EXCLUIDA ({excl})"
            elif is_fullscreen():
                extra = "  [pantalla completa]"
            print(f"  {str(app)[:20]:<20} | {str(titulo)[:52]:<52} | {clase:<12}{extra}")
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    print()
    return 0


def cmd_test_alert(args) -> int:
    cfg = load_config(perfil=args.profile)
    notifier = Notifier(cfg)
    print()
    for nivel in range(1, args.nivel + 1):
        print(f"  [Nivel {nivel}]")
        if nivel == 1:
            notifier.aviso("Prueba N1: aviso sutil (esta línea + un sonido corto suave).")
        elif nivel == 2:
            notifier.toast(
                "YourFocusGuard · prueba N2",
                "Así se ve el toast de Windows. Si lees esto en consola, winotify no está disponible.",
            )
        elif nivel == 3:
            notifier.voz("Hola, soy YourFocusGuard. Así suena el aviso de voz.")
        print()
    if not toast_disponible():
        print("  Nota: winotify no disponible en este sistema; el toast se degradó a consola.")
    return 0


def cmd_test_cam(args) -> int:
    cfg = load_config(perfil=args.profile)
    print()
    if not cfg.camara.habilitada:
        print("  La cámara está desactivada (privacidad por defecto).")
        print("  Para activarla, añade esto a config/user.toml:")
        print()
        print("    [camara]")
        print("    habilitada = true")
        print()
        return 1
    cam = CamaraWeb(cfg.camara)
    ok, detalle = cam.diagnostico()
    print(f"  Webcam: {detalle}")
    if not ok:
        print("  Revisa `indice` en [camara] o cierra la app que la esté usando.")
        print()
        return 1
    print("  La luz de la webcam se encenderá unos segundos: tomo UNA foto...")
    jpeg = cam.tomar_foto_jpeg()
    if not jpeg:
        print("  No se pudo tomar la foto (revisa el log en data/logs/agente.log).")
        print()
        return 1
    carpeta = cfg.ruta_fotos / datetime.now().strftime("%Y-%m-%d")
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{datetime.now().strftime('%H%M%S')}_prueba.jpg"
    ruta.write_bytes(jpeg)
    print(f"  Foto OK: {len(jpeg) // 1024} KB -> {ruta}")
    print("  Si salió oscura o con otra cámara, ajusta `indice` o `preframes` en [camara].")
    print()
    return 0


def cmd_doctor(args) -> int:
    resultados = []

    def check(nombre, ok, detalle="", critico=True):
        marca = "[OK]   " if ok else ("[FALLO] " if critico else "[AVISO] ")
        resultados.append((marca, nombre, detalle, ok, critico))

    print()
    print(f"  YourFocusGuard v{__version__} — diagnóstico")
    print("  " + "-" * 58)

    check("Python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    check("Sistema Windows", sys.platform == "win32", sys.platform, critico=False)

    try:
        cfg = load_config(perfil=args.profile)
        check("Configuración TOML", True, f"perfil={args.profile} · nube={cfg.cerebro.proveedor_nube}")
    except Exception as exc:
        check("Configuración TOML", False, str(exc))
        print()
        for marca, nombre, detalle, _, _ in resultados:
            print(f"  {marca} {nombre:<28} {detalle}")
        print()
        return 1

    if cfg.captura.habilitada:
        try:
            jpeg = grab_screen_jpeg(
                cfg.captura.monitor, cfg.captura.escala_max_ancho, cfg.captura.calidad_jpeg
            )
            check("Captura de pantalla (mss)", len(jpeg) > 1000, f"{len(jpeg) // 1024} KB por frame")
        except Exception as exc:
            check("Captura de pantalla (mss)", False, str(exc)[:70])
    else:
        # v0.5.0: en Modo Anclado no se captura nada; mss no es requisito.
        check(
            "Captura de pantalla (mss)",
            True,
            "no se usa en Modo Anclado (captura.habilitada = false)",
            critico=False,
        )

    app, titulo = get_active_window()
    check(
        "Ventana activa legible",
        app is not None,
        f"{app or '?'} · {(titulo or '')[:38]}",
        critico=False,
    )

    from yourfocusguard.capture.window_info import ventanas_visibles

    try:
        visibles = ventanas_visibles()
        monitores = len({v["monitor"] for v in visibles if v["monitor"]}) or 1
        check(
            "Ventanas visibles (multi-monitor)",
            True,
            f"{len(visibles)} ventanas en {monitores} monitor(es)",
            critico=False,
        )
    except Exception as exc:
        check("Ventanas visibles (multi-monitor)", False, str(exc)[:70], critico=False)

    from yourfocusguard.capture.idle import get_idle_seconds

    idle = get_idle_seconds()
    check(
        "Idle de entrada",
        idle is not None,
        f"{idle:.0f} s" if idle is not None else "no disponible fuera de Windows",
        critico=False,
    )

    if cfg.camara.habilitada:
        ok, detalle = CamaraWeb(cfg.camara).diagnostico()
        check("Webcam de verificación", ok, detalle, critico=False)
    else:
        check(
            "Webcam de verificación",
            True,
            "desactivada (opt-in: [camara] habilitada = true)",
            critico=False,
        )

    check("Toast de Windows (winotify)", toast_disponible(), "requiere Windows 10/11", critico=False)
    voces = voces_disponibles()
    check(
        "Voz TTS (pyttsx3)",
        bool(voces),
        ", ".join(voces[:3]) + ("..." if len(voces) > 3 else "") or "sin voces instaladas",
        critico=False,
    )

    proveedor = cfg.cerebro.proveedor_nube
    if proveedor == "gemini":
        tiene = bool(os.environ.get("GEMINI_API_KEY", "").strip())
        check("GEMINI_API_KEY en .env", tiene, "gratis en aistudio.google.com/apikey", critico=False)
        try:
            import google.genai  # noqa: F401

            check("SDK google-genai", True, f"modelo {cfg.cerebro.modelo_gemini}")
        except ImportError:
            check("SDK google-genai", False, "pip install google-genai", critico=False)
    elif proveedor == "openai":
        tiene = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        check("OPENAI_API_KEY en .env", tiene, "platform.openai.com/api-keys", critico=False)
        try:
            import openai  # noqa: F401

            check("SDK openai", True, f"modelo {cfg.cerebro.modelo_openai}")
        except ImportError:
            check("SDK openai", False, "pip install openai", critico=False)
    else:
        check("Cerebro", True, "solo Nivel B (heurística local)")

    try:
        db = EventDB(cfg.ruta_db)
        presupuesto = db.presupuesto_hoy()
        db.cerrar()
        check("SQLite escribible", True, f"{cfg.ruta_db} · hoy: {presupuesto:.3f} USD")
    except Exception as exc:
        check("SQLite escribible", False, str(exc)[:70])

    for marca, nombre, detalle, _, _ in resultados:
        print(f"  {marca} {nombre:<28} {detalle}")

    fallos = [r for r in resultados if not r[3] and r[4]]
    print("  " + "-" * 58)
    if fallos:
        print(f"  {len(fallos)} comprobación(es) críticas fallaron: revisa antes de arrancar.")
        print()
        return 1
    print("  Todo lo crítico está en orden. Ejecuta `python run.py start` para arrancar.")
    print()
    return 0


def cmd_export(args) -> int:
    cfg = load_config(perfil=args.profile)
    if not cfg.ruta_db.exists():
        print("Aún no hay base de datos (arranca el agente primero).")
        return 1
    db = EventDB(cfg.ruta_db)
    ruta = Path(args.salida) if args.salida else (
        cfg.carpeta_datos / f"yourfocusguard_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    )
    try:
        n = db.exportar_csv(ruta, dias=args.dias)
    finally:
        db.cerrar()
    print(f"{n} eventos de los últimos {args.dias} días exportados a: {ruta}")
    return 0


def cmd_purge(args) -> int:
    cfg = load_config(perfil=args.profile)
    if not args.si:
        print("Esto BORRA todos los eventos, sesiones y el consumo de API registrados.")
        print("Si estás seguro, repite el comando con --si")
        return 1
    if cfg.ruta_db.exists():
        db = EventDB(cfg.ruta_db)
        db.purgar_todo()
        db.cerrar()
    for ruta in (cfg.ruta_estado, cfg.ruta_control):
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass
    print("Base de eventos purgada (las imágenes nunca existieron: son solo RAM).")
    return 0


# --------------------------------------------------------------------------- #
# Comando auto: todo-en-uno
# --------------------------------------------------------------------------- #

def cmd_auto(args) -> int:
    """Modo todo-automático:

    1. Detecta las apps que estás usando durante N segundos.
    2. Declara una sesión con esas apps.
    3. Opcionalmente activa el modo máxima concentración.
    4. Arranca el agente (con panel web).
    """
    cfg = load_config(perfil=args.profile)
    setup_logging(cfg.registro.nivel, cfg.ruta_log)

    apps = []
    if args.detectar and args.detectar > 0:
        print()
        print(f"  Detectando apps durante {args.detectar:.0f} s…")
        print("  Cambia a tu programa de trabajo (Lightroom, Photoshop…).")
        muestras = window_info.apps_mas_usadas(
            args.detectar, 1.0, cfg.heuristica.apps_neutras, gracia=2.0
        )
        total = sum(n for _, n in muestras) or 1
        apps = [app for app, n in muestras if n / total >= 0.10][:5]
        if apps:
            print(f"  Detectadas: {', '.join(apps)}")
        else:
            print("  No se detectó ninguna app: sesión solo de inactividad.")

    # Declarar la sesión por archivo de control (el agente la lee en su primer ciclo)
    from yourfocusguard.config import escribir_user_toml
    ruta_user = cfg._config_dir or Path(".")
    # Guardar apps detectadas como predeterminadas de sesión
    overlay = {"sesion": {"apps": apps, "apps_auxiliares": list(cfg.sesion.apps_auxiliares)}}
    if args.concentracion:
        overlay["concentracion"] = {"habilitado": True}
    escribir_user_toml(ruta_user / "user.toml", overlay)

    _escribir_control(
        cfg,
        {
            "cmd": "session_start",
            "texto": args.texto,
            "apps": apps,
            "apps_aux": list(cfg.sesion.apps_auxiliares),
            "minutos": 0,
        },
    )
    if args.concentracion:
        _escribir_control(cfg, {"cmd": "privado", "valor": False})
        # El modo concentración se activa dentro del agente al leer [concentracion] habilitado=true
        print()
        print("  Modo máxima concentración: activado (hosts + audio).")

    print()
    print(f"  Sesión declarada: {args.texto!r}")
    print(f"    apps objetivo: {', '.join(apps) if apps else '(ninguna: solo regla de inactividad)'}")
    print("    mientras cumplas: cero capturas, cero nube.")
    print()
    print("  Arrancando el agente…")
    print()

    import logging
    log = logging.getLogger("yourfocusguard.auto")
    return _ejecutar_agente_con_servicios(cfg, args, log)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="YourFocusGuard: agente visual de productividad para TDAH (sprint 1, fases F0-F2).",
    )
    sub = parser.add_subparsers(dest="comando")

    p = sub.add_parser("start", help="arranca el agente (Ctrl+C para detener)")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.add_argument("--privado", action="store_true", help="solo Nivel B, cero nube")
    p.add_argument("--sin-panel", action="store_true", help="sin el panel web local")
    p.add_argument("--verbose", action="store_true", help="logging DEBUG")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser(
        "panel", help="abre el Panel del Guardián (configuración web local)"
    )
    p.add_argument("--puerto", type=int, default=None, help="puerto (8756 por defecto)")
    p.add_argument("--sin-abrir", action="store_true", help="no abrir el navegador")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_panel)

    p = sub.add_parser("mascota", help="la guardiana de escritorio (prueba de agente)")
    p.add_argument("--demo", action="store_true", help="cicla sus estados cada 3 s")
    p.add_argument("--tema", default=None, help="clasico | oscuro | calido")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_mascota)

    p = sub.add_parser("pause", help="pausa rápida (minutos, 15 por defecto)")
    p.add_argument("minutos", nargs="?", type=float, default=15.0)
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_pause)

    p = sub.add_parser("resume", help="reanuda tras una pausa manual")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_resume)

    p = sub.add_parser("sigo", help='"sigo en la tarea": cierra el aviso actual')
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_sigo)

    p = sub.add_parser("stop", help="detiene el agente limpiamente")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_stop)

    p = sub.add_parser("status", help="estado actual y resumen del día")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("task", help="declara (o consulta) la tarea de la sesión")
    p.add_argument("texto", nargs="?", default=None)
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_task)

    p = sub.add_parser("session", help="guardián de tarea: start / stop / status")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_session_status)
    ses = p.add_subparsers(dest="accion_sesion")

    ps = ses.add_parser("start", help="activa el guardián de tarea")
    ps.add_argument("texto", help='nombre de la tarea, p. ej. "editar fotos de la boda"')
    ps.add_argument(
        "--apps",
        default="",
        help="apps objetivo separadas por coma (proceso sin .exe; regex simple)",
    )
    ps.add_argument(
        "--aux",
        default="",
        help="apps toleradas que no cuentan como ausencia (explorer, bridge...)",
    )
    ps.add_argument(
        "--detectar",
        nargs="?",
        type=float,
        const=20.0,
        default=0.0,
        help="detecta solo las apps que estás usando (segundos; 20 por defecto)",
    )
    ps.add_argument("--min", type=float, default=0, help="duración en minutos; 0 = hasta session stop")
    ps.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    ps.set_defaults(fn=cmd_session_start)

    pp = ses.add_parser("stop", help="cierra la sesión y muestra el resumen")
    pp.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    pp.set_defaults(fn=cmd_session_stop)

    pst = ses.add_parser("status", help="cómo va la sesión activa")
    pst.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    pst.set_defaults(fn=cmd_session_status)

    p = sub.add_parser("inspect", help="muestra la ventana activa para armar tus listas")
    p.add_argument("segundos", nargs="?", type=float, default=20.0)
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_inspect)

    p = sub.add_parser("test-alert", help="dispara los niveles 1..N de la escalera")
    p.add_argument("nivel", nargs="?", type=int, choices=[1, 2, 3], default=3)
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_test_alert)

    p = sub.add_parser("test-cam", help="toma UNA foto con la webcam y la guarda")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_test_cam)

    p = sub.add_parser("doctor", help="diagnóstico de la instalación")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("export", help="exporta eventos a CSV (últimos N días)")
    p.add_argument("--salida", default=None, help="ruta del CSV")
    p.add_argument("--dias", type=int, default=7)
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("purge", help="borra todos los eventos registrados")
    p.add_argument("--si", action="store_true", help="confirma la purga")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_purge)

    p = sub.add_parser(
        "auto",
        help="Modo todo-automático: detecta apps, inicia sesión, activa concentración y arranca el agente",
    )
    p.add_argument("texto", nargs="?", default="sesión de enfoque",
                   help='nombre de la tarea, p. ej. "editar fotos"')
    p.add_argument("--detectar", nargs="?", type=float, const=20.0, default=20.0,
                   help="segundos de detección de apps (20 por defecto)")
    p.add_argument("--concentracion", action="store_true", default=False,
                   help="activar modo máxima concentración (bloquear hosts/audio)")
    p.add_argument("--sin-panel", action="store_true", help="sin el panel web local")
    p.add_argument("--profile", choices=["pc", "laptop"], default="pc")
    p.set_defaults(fn=cmd_auto)

    return parser


def main() -> int:
    parser = construir_parser()
    args = parser.parse_args()
    if not getattr(args, "fn", None):
        parser.print_help()
        return 0
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
