"""Motor del agente: bucle principal y máquina de estados de atención.

Cada ciclo (una captura) ejecuta las cinco fases del pipeline (blueprint,
cap. 3) y alimenta la máquina de estados del cap. 5:

    EN_ESPERA -> FOCO -> (señal autoritaria de desvío) -> ESCALADA
                       -> (voz emitida)                 -> COOLDOWN
                       -> (2 ciclos limpios consecutivos) -> FOCO
    cualquier estado -> PAUSA (manual / pomodoro / privado / ausencia)

Reglas anti-falso-positivo del cap. 5 implementadas aquí:
1. transiciones breves (< 2 frames) no escalan (heurística + histéresis);
2. vídeo a pantalla completa => modo silencioso automático;
4. exclusiones: ni se capturan ni se evalúan;
5. idle > 2 min => ciclos suspendidos.
(La regla 3, llamadas, aplica a la webcam y llega en F3.)
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from colorama import Fore, Style

from yourfocusguard import __version__
from yourfocusguard.actions import window_actions
from yourfocusguard.actions.concentracion import (
    ModoConcentracion,
    crear_modo_concentracion,
    limpiar_huerfanos_hosts,
)
from yourfocusguard.actions.escalation import Alerta, EscalationLadder
from yourfocusguard.actions.notifier import Notifier
from yourfocusguard.avatar.focus_bridge import crear_focus_bridge
from yourfocusguard.capture.presencia import crear_detector_presencia
from yourfocusguard.brain.base import Verdict
from yourfocusguard.brain.router import BrainRouter
from yourfocusguard.capture import idle as idle_mod
from yourfocusguard.capture import window_info
from yourfocusguard.capture.camera import CamaraWeb
from yourfocusguard.capture.screen import grab_screen_jpeg
from yourfocusguard.config import Config
from yourfocusguard.console_ui import banner_inicio, linea_ciclo, linea_evento
from yourfocusguard.core.commands import CommandProcessor
from yourfocusguard.constants import (
    Accion,
    Estado,
    HEARTBEAT_SEG,
    ORIGEN_SESION,
    TipoEvento,
)
from yourfocusguard.memory.fifo import FrameBuffer
from yourfocusguard.memory.models import FrameSnapshot
from yourfocusguard.privacy.exclusions import Exclusiones
from yourfocusguard.session_guard import (
    GuardianSesion,
    MOTIVO_FUERA,
    MOTIVO_INACTIVO,
    Presencia,
)
from yourfocusguard.storage.db import EventDB
from yourfocusguard.vigilante import VigilanteProhibiciones

log = logging.getLogger(__name__)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


_CARACTERES_ILEGALES = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _nombre_seguro(texto: str) -> str:
    """Convierte un motivo en un nombre de archivo válido en Windows."""
    limpio = _CARACTERES_ILEGALES.sub("-", str(texto or "")).strip(" .-")
    return (limpio or "foto")[:60]


class Agent:
    """El orquestador. Todas las dependencias externas son inyectables."""

    def __init__(
        self,
        cfg: Config,
        db: EventDB,
        router: BrainRouter,
        notifier: Notifier | None = None,
        exclusiones: Exclusiones | None = None,
        window_fn: Callable = window_info.get_active_window,
        idle_fn: Callable = idle_mod.get_idle_seconds,
        fullscreen_fn: Callable = window_info.is_fullscreen,
        visibles_fn: Callable | None = None,  # (patrones) -> set de apps visibles
        grab_fn: Callable | None = None,
        camara=None,  # inyectable para tests; por defecto según [camara]
        mascota="auto",  # "auto" | None | objeto con fijar_estado/al_alerta/parar
        frente_fn=None,  # v0.3.0: traer una app al frente (tests inyectan)
        minimizar_fn=None,  # v0.3.0: minimizar la ventana activa (bloqueo)
        bloqueo_fn=None,  # v0.5.0: ¿pantalla bloqueada? (tests inyectan)
        monitor_fn=None,  # v0.5.0: índice del monitor de la ventana al frente
        # v0.7.0 (Fase 3): modo máxima concentración, presencia y OpenPets bridge
        concentracion_fn=None,  # inyectable: ModoConcentracion
        presencia_fn=None,  # inyectable: DetectorPresencia
        focus_bridge=None,  # inyectable: FocusBridge (OpenPets Pet Assistant)
        reloj: Callable = time.time,
        dormir: Callable = time.sleep,
        consola: bool = True,
        hotkey: bool = True,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.router = router
        self.notifier = notifier or Notifier(cfg, consola=consola)
        self.exclusiones = exclusiones or Exclusiones(
            cfg.privacidad.apps_excluidas, cfg.privacidad.titulos_excluidos
        )
        self.window_fn = window_fn
        self.idle_fn = idle_fn
        self.fullscreen_fn = fullscreen_fn
        self.visibles_fn = visibles_fn or window_info.apps_visibles
        self.grab_fn = grab_fn or (
            lambda: grab_screen_jpeg(
                cfg.captura.monitor,
                cfg.captura.escala_max_ancho,
                cfg.captura.calidad_jpeg,
            )
        )
        self.reloj = reloj
        self.dormir = dormir
        self.consola = consola
        self.hotkey = hotkey
        # Webcam de verificación (v0.2.1): solo si está habilitada; los tests
        # inyectan un doble. La cámara nunca se abre sola: solo la pide el motor.
        if camara is not None:
            self.camara = camara
        elif cfg.camara.habilitada:
            self.camara = CamaraWeb(cfg.camara)
        else:
            self.camara = None

        # Avatar (v0.6.0): la cara del asistente. "auto" pregunta a la fábrica
        # (OpenPets si está abierto; si no, la mascota tkinter). El motor solo
        # usa la interfaz común: iniciar / fijar_estado / al_alerta / preguntar
        # / respuestas / parar.
        self.mascota = None
        if mascota == "auto":
            from yourfocusguard.avatar import crear_avatar

            self.mascota = crear_avatar(cfg)
        elif mascota is not None:
            self.mascota = mascota
        if self.mascota is not None and not getattr(self.mascota, "disponible", False):
            self.mascota.iniciar()

        # Medidas sobre ventanas (v0.3.0); inyectables para tests
        self.frente_fn = frente_fn or window_actions.traer_al_frente
        self.minimizar_fn = minimizar_fn or window_actions.minimizar_primera_plano
        # v0.5.0: ¿está la sesión bloqueada? (Win+L, UAC, suspensión)
        self.bloqueo_fn = bloqueo_fn or window_info.escritorio_bloqueado
        self.monitor_fn = monitor_fn or window_info.monitor_ventana_activa

        # v0.7.0 (Fase 3): modo máxima concentración y detección de presencia
        self.concentracion = (
            concentracion_fn
            if concentracion_fn is not None
            else crear_modo_concentracion(cfg.concentracion)
        )
        self.presencia = (
            presencia_fn
            if presencia_fn is not None
            else crear_detector_presencia(cfg.presencia)
        )
        # Modo sesión (guardián de tarea, v0.2.0)
        self.guardia = GuardianSesion(cfg.sesion, reloj)
        self.focus_bridge = focus_bridge
        if self.focus_bridge is not None:
            self.focus_bridge.sesion = self.guardia
            self.focus_bridge.agente_ref = lambda: self
        self._command_processor = CommandProcessor(self)
        self._ultima_presencia_ts: float | None = None

        # Vigilante de prohibiciones (v0.3.0): presupuestos diarios por primer plano
        self.vigilante = VigilanteProhibiciones(cfg, db, reloj)

        # Contadores del episodio para "traer al frente tras el N-avo llamado"
        self._llamados_episodio = 0
        self._frente_ya = False

        self.fifo = FrameBuffer(cfg.captura.fifo_frames)
        # El router y la escalera avisan de degradaciones a través del agente
        # para que queden registradas en SQLite con la sesión correcta.
        self.router.on_event = self._registrar_degradacion
        self.ladder = EscalationLadder(
            cfg.alertas, on_event=self._registrar_degradacion, reloj=reloj
        )

        # Máquina de estados
        self.estado = Estado.EN_ESPERA
        self.off_since: float | None = None
        self.clean_streak = 0
        self._hubo_veredicto_fuerte = False
        self.silencio_fs = False

        # Pausas y Pomodoro
        self.paused_until: float | None = None
        self._pausa_actual: str | None = None
        self.pom_fase = "foco"
        self.pom_acumulado = 0.0
        self.pom_ultimo_ts: float | None = None
        self.pom_fin_pausa: float | None = None
        self.pom_ciclos = 0

        # Varios
        self.tarea = ""
        self.sesion_id = ""
        self._last_heartbeat = 0.0
        self._ultimo_veredicto: Verdict | None = None
        self._last_app: str | None = None
        self._last_title: str | None = None
        self._parar = False
        self._hotkey_ok = False

        # Modo sesión (guardián de tarea, v0.2.0)
        self._sesion_motivo: str | None = None
        self._sesion_idle: float | None = None
        # Verificación con cámara (v0.2.1): una foto por episodio de inactividad
        self._idle_verificado_en: float | None = None
        self.fotos = 0

        # v0.5.0: respuesta del usuario y ausencia
        #   - pedidos que deja el atajo global (se aplican en el bucle, no en
        #     el hilo del teclado: nada de mutar estado desde otro hilo)
        #   - gracia de inactividad: "estoy leyendo" no cuenta como R2
        #   - reloj del último sondeo de sesión: detecta suspensión/reanudación
        self._pedido_sigo = False
        self._pedido_pausa_corta = False
        self._gracia_idle_hasta: float | None = None
        self._ultimo_sesion_ts: float | None = None
        self._pregunta_hecha = False
        # v0.5.0: una sesión declarada a mano manda sobre [sesion] apps
        # hasta que se cierre (el TOML no la pisa por debajo).
        self._anclas_manuales = False

        # v0.8.2: refuerzo positivo de enfoque continuo
        self._foco_continuo_desde: float | None = None
        self._ultimo_refuerzo_ts: float | None = None
        self._pausa_espera_confirmacion: bool = False
        self._ultimo_aviso_30min_ts: float | None = None
        self._foco_30min_sugerido: bool = False

        # v0.8.2: suscripción a consumo de API por voz / LLM
        try:
            from yourfocusguard.core.events import EVT_CONSUMO_API, subscribe
            subscribe(EVT_CONSUMO_API, self._al_consumo_api)
        except Exception:
            pass

    def _al_consumo_api(self, datos: dict) -> None:
        try:
            if hasattr(self, "db") and self.db and isinstance(datos, dict):
                self.db.registrar_consumo_voz(
                    segundos_audio=float(datos.get("segundos_audio", 0.0)),
                    tokens_llm=int(datos.get("tokens_llm", 0)),
                    coste_estimado=float(datos.get("coste_estimado", 0.0)),
                )
        except Exception as exc:
            log.debug("Error al persistir consumo api desde evento: %s", exc)

    # ------------------------------------------------------------------ #
    # Bucle principal
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        try:
            limpiar_huerfanos_hosts()
        except Exception as exc:
            log.debug("No se pudo limpiar hosts huérfano: %s", exc)
        self.sesion_id = self.db.abrir_sesion(self.cfg.agente.maquina, self.tarea)
        self.db.podar(self.cfg.datos.retencion_dias)
        self._evento(TipoEvento.INICIO, motivo=f"version:{__version__}")
        # Aplica comandos que quedaron pendientes (p. ej. un task declarado
        # antes de arrancar) para que el banner ya los refleje.
        self._procesar_control(self.reloj())
        if self.consola:
            banner_inicio(
                perfil=self.cfg.agente.perfil,
                maquina=self.cfg.agente.maquina,
                cerebro=self._descripcion_cerebro(),
                tarea=self.tarea,
                atajo=self.cfg.privacidad.atajo_pausa,
                intervalo=self.cfg.captura.intervalo_seg,
            )
        self._activar_hotkey()

        # v0.7.0 (Fase 3): conectar el puente OpenPets (Pet Assistant) si hay OpenPets
        if self.focus_bridge is not None:
            self.focus_bridge.iniciar()

        try:
            while not self._parar:
                inicio = self.reloj()
                try:
                    self._tick(inicio)
                except Exception:  # el agente nunca muere por un ciclo malo
                    log.exception("error en el ciclo; se continúa con el siguiente")
                    self._evento(TipoEvento.ERROR, motivo="excepcion_ciclo")
                    # dejar constancia en state.json aunque el ciclo fallara
                    # (p. ej. pantalla bloqueada o sesión remota desconectada)
                    self._escribir_estado(inicio)
                # Con sesión activa el ciclo pasa a sondeo de predicados
                # (5 s por defecto): más fino que el tick de captura y sin imágenes.
                base = (
                    self.cfg.sesion.intervalo_sondeo
                    if self.guardia.activa
                    else self.cfg.captura.intervalo_seg
                )
                resto = base - (self.reloj() - inicio)
                self.dormir(max(1.0, resto))
        except KeyboardInterrupt:
            if self.consola:
                linea_evento("deteniendo el agente (Ctrl+C)...", Fore.CYAN)
        finally:
            self._apagar()

    def _apagar(self) -> None:
        self.ladder.end(self.reloj())
        if self.mascota is not None:
            self.mascota.parar()
        # v0.7.0: desconectar el puente OpenPets y desactivar concentración
        if self.focus_bridge is not None:
            self.focus_bridge.parar()
        if self.concentracion is not None and self.concentracion.activo:
            self.concentracion.desactivar()
        try:
            from yourfocusguard.core.events import EVT_CONSUMO_API, unsubscribe
            unsubscribe(EVT_CONSUMO_API, self._al_consumo_api)
        except Exception:
            pass
        try:
            self.notifier.cerrar()  # v0.5.0: cierra el hilo de voz
        except Exception:  # pragma: no cover
            pass
        if self.sesion_id:
            self._evento(TipoEvento.FIN, motivo=f"ciclos_pomodoro:{self.pom_ciclos}")
            self.db.cerrar_sesion(self.sesion_id, self.pom_ciclos)
        self._escribir_estado(self.reloj(), detenido=True)
        if self._hotkey_ok:
            try:
                import keyboard

                keyboard.unhook_all()
            except Exception:
                pass
        self.db.cerrar()
        if self.consola:
            linea_evento(
                f"sesión cerrada · eventos en {self.db.ruta}", Fore.CYAN
            )

    # ------------------------------------------------------------------ #
    # Un ciclo de captura
    # ------------------------------------------------------------------ #

    def _tick(self, ahora: float | None = None) -> dict:
        ahora = self.reloj() if ahora is None else ahora
        self._procesar_control(ahora)
        if self._parar:
            return {"estado": "DETENIDO"}
        self._atender_pedidos(ahora)
        self._verificar_scheduler(ahora)

        # v0.7.1: modo concentración con duración — si pasó el tiempo preset,
        # se desactiva solo (salvo que sea 0 = hasta próximo reinicio).
        if (
            self.concentracion.activo
            and self.cfg.concentracion.duracion_min > 0
            and self.concentracion.duracion_seg() >= self.cfg.concentracion.duracion_min * 60
        ):
            self.concentracion.desactivar()
            if self.consola:
                linea_evento(
                    "modo concentración finalizado (tiempo cumplido)", Fore.YELLOW
                )

        # v0.3.0: edición en vivo desde el panel (user.toml) en el mismo ciclo
        self.cfg.refrescar_si_cambia()

        # v0.4.0: capturas fuera del mapa -> Modo Anclado permanente. Si la
        # captura de pantalla está deshabilitada, el agente vive en modo
        # sesión: primer plano + idle mandan; se reactiva solo si lo detienen.
        if not self.cfg.captura.habilitada and not self.guardia.activa:
            self._activar_modo_anclado(ahora)

        app, titulo = self.window_fn()
        self._last_app, self._last_title = app, titulo

        # v0.3.0: presupuestos de prohibiciones (cuenta el primer plano;
        # en ventanas excluidas el agente finge no estar, igual que siempre)
        self._vigilar(ahora, app, titulo)

        # 1) pausa manual (atajo global o comando `pause`)
        if self.paused_until is not None:
            if ahora >= self.paused_until:
                if self._pausa_espera_confirmacion:
                    # Pausa protegida: los 10 min concluyeron, pero espera confirmación explícita
                    return self._tick_en_pausa(ahora, "manual", detalle="esperando confirmacion")
                self._reanudar(ahora, "manual")
            else:
                return self._tick_en_pausa(ahora, "manual")

        # 2) pausa Pomodoro
        if self.pom_fase in ("pausa", "pausa_larga"):
            if self.pom_fin_pausa is not None and ahora >= self.pom_fin_pausa:
                self._fin_pausa_pomodoro(ahora)
            else:
                return self._tick_en_pausa(ahora, "pomodoro")

        # 2.b) modo sesión: vigilancia por predicados, SIN capturas ni nube.
        # (Las pausas manual y Pomodoro ya se atendieron arriba: durante una
        # pausa el guardián tampoco molesta, y al reanudar se resetea su reloj.)
        if self.guardia.activa:
            return self._tick_sesion(ahora, app, titulo)

        # 3) exclusiones de privacidad: ni capturar ni evaluar
        patron = self.exclusiones.excluida(app, titulo)
        if patron:
            return self._tick_en_pausa(ahora, "privado", detalle=patron)
        if self._pausa_actual == "privado":
            self._reanudar(ahora, "privado")

        # 4) ausencia (idle > umbral): ciclos suspendidos
        idle = self.idle_fn()
        if idle is not None and idle > self.cfg.heuristica.idle_ausencia_seg:
            return self._tick_en_pausa(ahora, "ausencia", detalle=f"idle {idle:.0f}s")
        if self._pausa_actual == "ausencia":
            self._reanudar(ahora, "ausencia")

        # 5) captura -> FIFO -> cerebro
        jpeg = self.grab_fn()
        snap = FrameSnapshot(
            ts=ahora,
            app=app,
            title=titulo,
            idle_seconds=idle,
            jpeg=jpeg,
            fullscreen=self.fullscreen_fn(),
        )
        self.fifo.push(snap)

        veredicto = self.router.analyze(self.fifo, self.tarea)
        snap.verdict = veredicto
        self._ultimo_veredicto = veredicto

        self._actualizar_estado(ahora, veredicto, snap)
        self._escalar_si_toca(ahora, veredicto)
        self._pomodoro_avanzar(ahora)
        self._comprobar_refuerzo_positivo(ahora)
        self._latido(ahora, veredicto)
        self._escribir_estado(ahora)

        if self.consola:
            linea_ciclo(
                ahora, self.estado, app, titulo,
                veredicto.origen, veredicto.confianza, idle,
            )
        return {
            "estado": self.estado.value,
            "origen": veredicto.origen,
            "desvio": veredicto.desvio,
            "confianza": veredicto.confianza,
            "pausa": self._pausa_actual,
        }

    # ------------------------------------------------------------------ #
    # Prohibiciones: presupuestos diarios + bloqueo activo (v0.3.0)
    # ------------------------------------------------------------------ #

    def _vigilar(self, ahora: float, app, titulo) -> None:
        """Un ciclo del vigilante: acumular, avisar al agotarse y bloquear.

        Se llama en TODOS los modos (monitoreo y sesión) y también durante
        las pausas: el presupuesto se consume igual, pero en pausa no se
        ejecuta el bloqueo ni el toast (el usuario pidió silencio). En las
        ventanas excluidas de privacidad no se cuenta absolutamente nada.
        """
        if app is None and titulo is None:
            return
        if self.exclusiones.excluida(app, titulo):
            return
        en_pausa = (
            self.paused_until is not None
            or self.pom_fase in ("pausa", "pausa_larga")
        )
        avisos = self.vigilante.tick(ahora, app, titulo)
        if avisos and not en_pausa:
            for aviso in avisos:
                self.notifier.toast(
                    "YourFocusGuard · presupuesto agotado",
                    f"{aviso.patron}: llegaste al límite de {aviso.limite_min} min "
                    f"de hoy. Ya no cuentes con eso hasta mañana.",
                )
                if self.mascota is not None:
                    self.mascota.al_alerta(2, f"{aviso.patron}: límite del día")
                self._evento(
                    TipoEvento.ALERTA,
                    accion=Accion.TOAST.value,
                    motivo=f"prohibicion:{aviso.patron}:{aviso.limite_min}min",
                )
                if self.consola:
                    linea_evento(
                        f"presupuesto agotado: {aviso.patron} "
                        f"({aviso.usado_min:.0f} min de {aviso.limite_min})",
                        Fore.RED,
                    )
        if en_pausa:
            return
        # Bloqueo activo: mientras esté agotada y al frente, se minimiza
        entrada = self.vigilante.debe_bloquear(app, titulo)
        if entrada is not None and self.minimizar_fn():
            self._quizas_traer_al_frente(ahora, forzar=True)

        # v0.7.0 (Fase 3): modo máxima concentración — minimizar apps bloqueadas
        if self.concentracion.activo and self.concentracion.debe_minimizar(app, titulo):
            if self.minimizar_fn():
                self._evento(
                    TipoEvento.ALERTA,
                    accion="minimizar",
                    motivo=f"concentracion:{app or '?'}:{titulo or ''}",
                )
                if self.consola:
                    linea_evento(
                        f"concentración: minimizando {app or '?'}", Fore.RED
                    )

    def _app_objetivo_frente(self) -> str:
        """App a traer al frente: la fija el panel o, si no, la 1.ª de la sesión."""
        target = (self.cfg.alertas.traer_al_frente_app or "").strip()
        if not target and self.guardia.activa and self.guardia.apps:
            target = self.guardia.apps[0]
        return target

    def _quizas_traer_al_frente(self, ahora: float, forzar: bool = False) -> None:
        """Modo completo: tras el N-avo llamado, la app de trabajo vuelve al frente.

        v0.5.0: además del número de llamados, se exige que el desvío lleve
        ``minutos_antes_de_traer`` — traerte la ventana a los 30 s no es un
        "segundo aviso", es un secuestro del ratón.
        """
        if self._frente_ya and not forzar:
            return
        if not forzar:
            if self.cfg.alertas.modo != "completo":
                return
            if self._llamados_episodio < self.cfg.alertas.traer_al_frente_tras:
                return
            minutos = max(0.0, self.cfg.alertas.minutos_antes_de_traer)
            if (
                self.off_since is not None
                and minutos > 0
                and (ahora - self.off_since) < minutos * 60
            ):
                return
        target = self._app_objetivo_frente()
        if not target:
            return
        ventana = self.frente_fn(target)
        if ventana:
            primera_vez = not self._frente_ya
            self._frente_ya = True
            if primera_vez:  # se anuncia y registra una sola vez por episodio
                if self.consola:
                    linea_evento(
                        f"medida: {target} vuelve al frente ({ventana[:40]})",
                        Fore.CYAN,
                    )
                self._evento(
                    TipoEvento.ALERTA,
                    accion="traer_al_frente",
                    motivo=f"target:{target}",
                )
                self._decir("Es momento de seguir trabajando.", voz=True, nivel=2)
        else:
            log.debug("traer_al_frente: sin ventana para %r", target)

    def _decir(self, texto: str, voz: bool = True, nivel: int = 1) -> None:
        """Frase del asistente por los canales configurados (sin duplicar)."""
        if self.mascota is not None:
            self.mascota.al_alerta(nivel, texto)
        if voz and self.cfg.alertas.modo in ("visual_sonoro", "completo"):
            self.notifier.voz(texto)
        if self.consola:
            linea_evento(f"asistente: {texto}", Fore.CYAN)


    # ------------------------------------------------------------------ #
    # Modo Anclado (v0.4.0): vigilancia por primer plano + idle, sin capturas
    # ------------------------------------------------------------------ #

    def _activar_modo_anclado(self, ahora: float) -> None:
        """Arranca (o re-arranca) el guardián de tarea como modo por defecto.

        Usa las apps de [sesion] (si el usuario no declaró ninguna, el
        guardián funciona como vigilante genérico de inactividad: R2 sola).
        Nunca lanza y no reinicia una sesión ya activa.
        """
        self.guardia.iniciar(ahora, self.cfg.sesion.apps, self.cfg.sesion.apps_auxiliares)
        self._ultimo_sesion_ts = ahora
        self._gracia_idle_hasta = None
        self._pregunta_hecha = False
        self._anclas_manuales = False
        apps = ", ".join(self.guardia.apps) if self.guardia.apps else "(solo inactividad)"
        if self.consola:
            linea_evento(
                f"modo anclado activo: sin capturas ni nube · anclas: {apps}",
                Fore.CYAN,
            )
        self._evento(TipoEvento.INICIO, motivo=f"modo_anclado:{apps}")

    def _sincronizar_anclas(self, ahora: float) -> None:
        """Aplica los cambios de ``[sesion] apps`` en caliente (v0.5.0).

        El panel y el editor de ``user.toml`` escriben la configuración; el
        agente la recarga cada ciclo, pero el guardián compilaba sus patrones
        una sola vez. Aquí se recompilan sin reiniciar la sesión. Una sesión
        declarada a mano (``session start --apps``) manda sobre el TOML.
        """
        if self._anclas_manuales:
            return
        configuradas = self.cfg.sesion.apps
        if not configuradas:
            return  # nunca vaciar por accidente las anclas de una sesión manual
        if self.guardia.reconfigurar(
            ahora, configuradas, self.cfg.sesion.apps_auxiliares
        ):
            apps = ", ".join(self.guardia.apps)
            self._evento(TipoEvento.TAREA, motivo=f"anclas_actualizadas:{apps}")
            if self.consola:
                linea_evento(f"anclas actualizadas en vivo: {apps}", Fore.CYAN)

    def _pregunta_contextual(self, presencia: Presencia, senal: str) -> None:
        """Al abrir un episodio, el asistente pregunta con contexto (v0.4.0).

        Petición del usuario: si la cámara está habilitada tomó una foto para
        entender qué pasa (hijo, teléfono, leyendo) y pregunta acorde; si no,
        pregunta directo ("¿qué estás haciendo? ¿necesitas una pausa?").
        Respeta los canales de alertas.modo: la mascota siempre (visual),
        el sonido en visual_sonoro/completo, toast+voz solo en completo.
        """
        if self._pregunta_hecha:      # una pregunta por episodio
            return
        con_foto = (
            self.camara is not None
            and self.cfg.camara.foto_en_disparo
            and presencia != Presencia.EXCLUIDA
            and not self.cfg.modo_privado
        )
        if senal == MOTIVO_INACTIVO:
            if con_foto:
                texto = (
                    "Llevas un rato sin tocar nada: te tomé una foto para "
                    "entender qué está pasando. ¿Qué estás haciendo? "
                    "¿Necesitas hacer una pausa?"
                )
            else:
                texto = (
                    "Llevas un rato sin tocar nada. ¿Qué estás haciendo "
                    "en este momento? ¿Necesitas hacer una pausa?"
                )
        else:
            anclas = ", ".join(self.guardia.apps) if self.guardia.apps else "tu tarea"
            texto = f"Ya no estás en {anclas}. ¿Volvemos a la tarea?"

        # v0.5.0: la pregunta lleva respuestas. Si el avatar puede preguntar
        # (ventana con botones), pregunta él; si no, quedan los atajos
        # Ctrl+Alt+F11 / F10 como canal de respuesta.
        self._pregunta_hecha = True
        opciones = [
            ("sigo", "Sigo aquí"),
            ("pausa", f"Pausa {self.cfg.privacidad.pausa_corta_min} min"),
            ("leyendo", "Estoy leyendo"),
        ]
        preguntado = False
        if self.mascota is not None and hasattr(self.mascota, "preguntar"):
            try:
                self.mascota.preguntar(texto, opciones)
                preguntado = True
            except Exception:  # pragma: no cover - el avatar nunca tumba al motor
                log.exception("el avatar no pudo mostrar la pregunta")
        if self.mascota is not None and not preguntado:
            self.mascota.al_alerta(1, texto)
        modo = self.cfg.alertas.modo
        if modo in ("visual_sonoro", "completo"):
            self.notifier.aviso(texto)
        if modo == "completo":
            self.notifier.toast("YourFocusGuard", texto)
            self.notifier.voz(texto)
        self._evento(
            TipoEvento.ALERTA,
            accion="pregunta_contextual",
            motivo=f"{senal}:foto" if con_foto else f"{senal}:verbal",
            origen=ORIGEN_SESION,
        )

    # ------------------------------------------------------------------ #
    # Respuesta del usuario (v0.5.0): atajos, avatar y CLI
    # ------------------------------------------------------------------ #

    def _pedir_sigo(self) -> None:
        """Callback del atajo: solo levanta la bandera (otro hilo)."""
        self._pedido_sigo = True

    def _pedir_pausa_corta(self) -> None:
        self._pedido_pausa_corta = True

    def _atender_pedidos(self, ahora: float) -> None:
        """Aplica lo que pidió el teclado, el avatar o la CLI (en el bucle)."""
        if self._pedido_pausa_corta:
            self._pedido_pausa_corta = False
            minutos = self.cfg.privacidad.pausa_corta_min
            self.paused_until = ahora + minutos * 60
            self._tick_en_pausa(ahora, "manual", detalle=f"atajo, {minutos} min")
            return
        for clave in self._respuestas_avatar():
            self._responder_pregunta(clave, ahora)
        if self._pedido_sigo:
            self._pedido_sigo = False
            self.confirmar_sigo(ahora)

    def _verificar_scheduler(self, ahora: float) -> None:
        """Verifica y dispara recordatorios y rutinas en tiempo real (v0.8.3 Fase 3)."""
        try:
            from yourfocusguard.core.scheduler import obtener_scheduler
            scheduler = obtener_scheduler(self.cfg)
            avisos = scheduler.verificar_pendientes()
            for aviso in avisos:
                self._decir(aviso, voz=True, nivel=1)
        except Exception as exc:
            log.debug("Error al verificar scheduler: %s", exc)

    def _respuestas_avatar(self) -> list[str]:
        """Drena las respuestas que dejó la mascota (thread-safe en ella)."""
        if self.mascota is None or not hasattr(self.mascota, "respuestas"):
            return []
        try:
            return list(self.mascota.respuestas())
        except Exception:  # pragma: no cover
            log.exception("no se pudieron leer las respuestas del avatar")
            return []

    def _responder_pregunta(self, clave: str, ahora: float) -> None:
        """Traduce la respuesta del usuario a una acción del motor."""
        clave = (clave or "").strip().lower()
        if clave in ("sigo", "continuar", "seguir"):
            self._pausa_espera_confirmacion = False
            if self.paused_until is not None:
                self.paused_until = None
                self._reanudar(ahora, "manual")
            self.confirmar_sigo(ahora)
        elif clave == "leyendo":
            # Leer/estudiar es trabajo: damos 5 min de gracia al reloj de idle
            # sin cerrar la regla de "fuera de la app".
            self.confirmar_sigo(ahora)
            self._gracia_idle_hasta = ahora + 5 * 60
            self._decir("Perfecto, te dejo leer cinco minutos.", voz=False)
        elif clave in ("pausa", "pausa 10m", "pausar"):
            minutos = 10.0
            self.paused_until = ahora + minutos * 60
            self._pausa_espera_confirmacion = True
            self._tick_en_pausa(ahora, "manual", detalle=f"respuesta, {minutos:.0f} min (protegida)")
        elif clave in ("+15m", "extender 15m", "15m mas"):
            self._foco_30min_sugerido = True
            self.confirmar_sigo(ahora)
            self._decir("Genial, seguimos 15 minutos más.", voz=True)
        else:
            log.debug("respuesta de avatar desconocida: %r", clave)

    def confirmar_sigo(self, ahora: float, gracia_seg: float = 60.0) -> None:
        """'Sigo en la tarea': cierra el episodio en silencio y rearma relojes.

        La gracia (60 s por defecto) evita el bucle absurdo de "digo que sigo
        y el reloj de inactividad me vuelve a llamar en el mismo tick".
        """
        if self.off_since is not None:
            self.ladder.end(ahora)
            self._evento(
                TipoEvento.RETOMA,
                estado=Estado.FOCO.value,
                motivo="confirmado_por_usuario",
                origen=ORIGEN_SESION,
            )
            self.off_since = None
            self._llamados_episodio = 0
            self._frente_ya = False
            self.clean_streak = 0
            self._sesion_motivo = None
        self._pregunta_hecha = False
        self._idle_verificado_en = None
        if gracia_seg > 0:
            self._gracia_idle_hasta = max(
                self._gracia_idle_hasta or 0.0, ahora + gracia_seg
            )
        if self.guardia.activa:
            self.guardia.reanudar(ahora)
        self.estado = Estado.FOCO
        self._decir("Vale, sigo contigo. A la tarea.", voz=False)

    # ------------------------------------------------------------------ #
    # Modo sesión: guardián de tarea (v0.2.0)
    # ------------------------------------------------------------------ #

    def _tick_sesion(self, ahora: float, app: str | None, titulo: str | None) -> dict:
        """Ciclo del modo sesión: sondea predicados y alimenta la escalera.

        Diferencias con el pipeline normal: no hay captura de pantalla ni
        cerebro mientras las reglas se cumplan; solo al disparar se toma UNA
        captura de evidencia (en F3 será la foto de webcam que propuso el
        usuario). La máquina de estados, la escalera y el registro se reutilizan.

        v0.5.0: antes de evaluar nada se comprueba si el usuario está
        realmente ahí (pantalla bloqueada, suspensión o idle largo). Si no
        está, el guardián se pausa solo y no dispara nada; al volver, se
        reanuda limpio y sin avalancha de avisos.
        """
        # fin programado de la sesión
        if self.guardia.fin is not None and ahora >= self.guardia.fin:
            self._terminar_sesion(ahora, "tiempo_agotado")
            return {"estado": self.estado.value, "sesion": "cerrada"}

        # v0.5.0: anclas editables en vivo desde el panel o user.toml
        self._sincronizar_anclas(ahora)

        # --- ausencia real: pantalla bloqueada / suspensión / sin input -----
        gap = 0.0 if self._ultimo_sesion_ts is None else ahora - self._ultimo_sesion_ts
        self._ultimo_sesion_ts = ahora
        umbral_ausencia = self.cfg.sesion.ausencia_seg
        presencia = self._presencia(app, titulo)
        idle = None if presencia == Presencia.EXCLUIDA else self.idle_fn()
        self._sesion_idle = idle
        bloqueado = bool(umbral_ausencia and self.bloqueo_fn())
        if umbral_ausencia and (
            bloqueado
            or gap >= umbral_ausencia
            or (idle is not None and idle >= umbral_ausencia)
        ):
            detalle = (
                "pantalla bloqueada" if bloqueado
                else f"sin input {idle:.0f}s" if idle is not None and idle >= umbral_ausencia
                else f"pausa de {gap:.0f}s"
            )
            return self._tick_en_pausa(ahora, "ausencia", detalle=detalle)
        if self._pausa_actual == "ausencia":
            self._reanudar(ahora, "ausencia")

        # v0.7.0 (Fase 3): detección de presencia física — si no hay rostro
        # detectado durante umbral_presencia, pausar la sesión sola.
        if (
            self.cfg.presencia.habilitada
            and self.presencia.disponible()
            and self.guardia.activa
        ):
            umbral_pres = self.cfg.presencia.ausente_para_pausar_seg
            if umbral_pres and umbral_pres > 0:
                ahora_pres = self.reloj()
                if (
                    self._ultima_presencia_ts is None
                    or ahora_pres - self._ultima_presencia_ts >= umbral_pres
                ):
                    self._ultima_presencia_ts = ahora_pres
                    det = self.presencia.evaluar()
                    if not det.en_silla and not det.error:
                        return self._tick_en_pausa(
                            ahora, "ausencia", detalle="presencia: no se detecta usuario"
                        )

        # --- gracia de inactividad ("estoy leyendo") ------------------------
        en_gracia = self._gracia_idle_hasta is not None and ahora < self._gracia_idle_hasta
        if not en_gracia:
            self._gracia_idle_hasta = None
        idle_regla = None if en_gracia else idle
        ev = self.guardia.evaluar(ahora, presencia, idle_regla)

        # R0 · verificación suave (v0.2.1): en la tarea pero congelado N s.
        # Propuesta del usuario: "si pasan más de 20 s sin tocar mouse ni
        # teclado, hace UNA foto con la cámara para verificar". Silenciosa:
        # no abre episodio ni toca la escalera; se rearma cuando vuelve el input.
        if (
            self.off_since is None
            and not en_gracia
            and self.camara is not None
            and self.cfg.sesion.verificar_con_camara_seg > 0
            and idle is not None
            and idle >= self.cfg.sesion.verificar_con_camara_seg
            and presencia in (Presencia.EN_APP, Presencia.VISIBLE, Presencia.AUXILIAR)
        ):
            if self._idle_verificado_en is None:
                self._idle_verificado_en = ahora
                if self.consola:
                    linea_evento(
                        f"sin input {idle:.0f} s · foto de verificación (cámara)",
                        Fore.CYAN,
                    )
                self._tomar_foto_camara("verificacion_idle")
        elif idle is not None and idle < self.cfg.sesion.verificar_con_camara_seg:
            self._idle_verificado_en = None  # hubo input: rearmar el chequeo

        # apertura de episodio: backdating honesto (t0 = cuándo se rompió la regla)
        if ev.senal and self.off_since is None:
            self.off_since = max(self.guardia.inicio, ahora - ev.sostenido_seg)
            self._hubo_veredicto_fuerte = True
            self._sesion_motivo = ev.senal
            self.guardia.disparos += 1
            self._idle_verificado_en = None
            self._pregunta_hecha = False
            # La pregunta contextual ES el primer llamado (v0.5.0): N0 y N1
            # quedan cubiertos para que no vuelvan a sonar a los 20 y 30 s.
            self.ladder.begin(ahora, niveles_cubiertos=(0, 1))
            self._capturar_evidencia_sesion(presencia, ev.senal)
            self._pregunta_contextual(presencia, ev.senal)
            if self.consola:
                linea_evento(
                    f"regla de sesión disparada: {ev.senal} "
                    f"({ev.sostenido_seg:.0f} s sostenidos)",
                    Fore.YELLOW,
                )
        elif ev.senal:
            self._sesion_motivo = ev.senal

        veredicto = self._veredicto_sesion(ahora, ev)
        self._ultimo_veredicto = veredicto
        # El silencio por pantalla completa solo aplica si lo que está a
        # pantalla completa NO es una app de la sesión (un vídeo, no el editor).
        fs = self.fullscreen_fn() if presencia == Presencia.FUERA else False
        snap = FrameSnapshot(
            ts=ahora, app=app, title=titulo, idle_seconds=idle, fullscreen=fs
        )
        self._actualizar_estado(ahora, veredicto, snap)
        self._escalar_si_toca(ahora, veredicto)
        self._pomodoro_avanzar(ahora)
        self._comprobar_refuerzo_positivo(ahora)
        self._latido(ahora, veredicto)
        self._escribir_estado(ahora)

        if self.consola:
            linea_ciclo(
                ahora, self.estado, app, titulo,
                veredicto.origen, veredicto.confianza, idle,
            )
        return {
            "estado": self.estado.value,
            "origen": veredicto.origen,
            "sesion": "activa",
            "presencia": presencia.value,
        }

    def _presencia(self, app: str | None, titulo: str | None) -> Presencia:
        """Clasifica el tick actual según primer plano + ventanas visibles.

        Con ``sesion.exigir_primer_plano = true`` (v0.5.0) una app visible en
        el otro monitor NO cuenta como presente: es la petición literal
        "quiero que Lightroom esté al frente". Por defecto se mantiene la
        tolerancia para consultar referencias en el segundo monitor.
        """
        g = self.guardia
        if app:
            if self.exclusiones.excluida(app, titulo):
                return Presencia.EXCLUIDA
            if g.matchea_objetivo(app):
                objetivo = self.cfg.sesion.monitor_objetivo
                if objetivo and self.monitor_fn() not in (0, objetivo):
                    return Presencia.FUERA
                return Presencia.EN_APP
        if g.apps and not self.cfg.sesion.exigir_primer_plano and self.visibles_fn(g.apps):
            # app objetivo viva en OTRO monitor aunque no esté al frente:
            # no se castiga mirar una referencia (blueprint multi-monitor)
            return Presencia.VISIBLE
        if app and g.matchea_auxiliar(app):
            return Presencia.AUXILIAR
        return Presencia.FUERA

    def _veredicto_sesion(self, ahora: float, ev) -> Verdict:
        desvio = ev.senal is not None
        motivo = ev.senal or (self._sesion_motivo if self.off_since is not None else "ninguno")
        return Verdict(
            continuidad=not desvio,
            desvio=desvio,
            motivo=motivo,
            app_detectada=self._last_app or "",
            confianza=0.9,  # los predicados del SO son autoritarios
            accion_sugerida="nada",
            origen=ORIGEN_SESION,
            ts=ahora,
        )

    def _capturar_evidencia_sesion(self, presencia: Presencia, senal: str) -> None:
        """UNA captura de constancia al abrir el episodio (nunca en excluded).

        v0.2.1: si la webcam está habilitada, además de la captura de
        pantalla se toma UNA foto de verificación — es la propuesta del
        usuario: la cámara como constancia del disparo, no como vigilancia
        continua.
        """
        if not self.cfg.sesion.capturar_al_disparar and self.camara is None:
            return
        if presencia == Presencia.EXCLUIDA or self.cfg.modo_privado:
            return
        try:
            if self.cfg.sesion.capturar_al_disparar:
                jpeg = self.grab_fn()
                kb = len(jpeg) // 1024 if jpeg else 0
                self._evento(
                    TipoEvento.DETECCION,
                    motivo=f"evidencia:{senal}:{kb}kb",
                    confianza=0.9,
                    accion="captura",
                    origen=ORIGEN_SESION,
                )
            if self.camara is not None and self.cfg.camara.foto_en_disparo:
                self._tomar_foto_camara(f"disparo:{senal}")
        except Exception:
            log.exception("no se pudo tomar la evidencia de sesión")

    # ------------------------------------------------------------------ #
    # Cámara de verificación (v0.2.1)
    # ------------------------------------------------------------------ #

    def _tomar_foto_camara(self, motivo: str) -> None:
        """Una foto de webcam, con registro y guardado opcional.

        Nunca lanza: si la cámara falla se registra ``camara:...:falla`` y
        el guardián sigue funcionando por predicados igual que siempre.
        """
        if self.camara is None:
            return
        jpeg = None
        try:
            jpeg = self.camara.tomar_foto_jpeg()
        except Exception:
            log.exception("la webcam falló al tomar la foto")
        kb = len(jpeg) // 1024 if jpeg else 0
        guardada: str | None = None
        if jpeg and self.cfg.camara.guardar_fotos:
            guardada = self._guardar_foto(jpeg, motivo)
            self.fotos += 1
        self._evento(
            TipoEvento.DETECCION,
            motivo=f"camara:{motivo}:{kb}kb" if jpeg else f"camara:{motivo}:falla",
            confianza=0.9,
            accion="foto",
            origen=ORIGEN_SESION,
        )
        if self.consola:
            linea_evento(
                f"foto de webcam ({motivo}): {kb} KB"
                + (f" · {guardada}" if guardada else ""),
                Fore.CYAN,
            )

    def _guardar_foto(self, jpeg: bytes, motivo: str) -> str | None:
        """Guarda la foto en data/fotos/AAAA-MM-DD/HHMMSS_motivo.jpg.

        v0.5.0: el motivo se sanea. En Windows los dos puntos son ilegales en
        un nombre de archivo y ``motivo`` trae "disparo:inactivo_en_app", que
        hacía fallar el guardado (WinError 87) en silencio.
        """
        try:
            ahora = datetime.now()
            carpeta = self.cfg.ruta_fotos / ahora.strftime("%Y-%m-%d")
            carpeta.mkdir(parents=True, exist_ok=True)
            nombre = _nombre_seguro(motivo)
            ruta = carpeta / f"{ahora.strftime('%H%M%S')}_{nombre}.jpg"
            tmp = ruta.with_suffix(".tmp")
            tmp.write_bytes(jpeg)
            tmp.replace(ruta)
            return str(ruta)
        except OSError:
            log.exception("no se pudo guardar la foto de webcam")
            return None

    def _podar_fotos(self) -> None:
        """Borra carpetas de fotos por día más viejas que la retención."""
        dias = self.cfg.camara.retencion_dias
        if dias <= 0:
            return
        limite = time.time() - dias * 86400
        raiz = self.cfg.ruta_fotos
        try:
            if not raiz.exists():
                return
            for carpeta in raiz.iterdir():
                if carpeta.is_dir() and carpeta.stat().st_mtime < limite:
                    shutil.rmtree(carpeta, ignore_errors=True)
                    log.info("poda de fotos: %s eliminada", carpeta.name)
        except OSError:
            log.exception("no se pudo podar la carpeta de fotos")

    def _iniciar_sesion(self, ahora: float, data: dict) -> None:
        apps = [str(a).strip().lower() for a in (data.get("apps") or []) if str(a).strip()]
        aux = [str(a).strip().lower() for a in (data.get("apps_aux") or []) if str(a).strip()]
        minutos = float(data.get("minutos") or 0)
        texto = (data.get("texto") or "").strip()
        self.guardia.iniciar(ahora, apps, apps_aux=aux, minutos=minutos or None)
        self._sesion_motivo = None
        self._idle_verificado_en = None
        self._ultimo_sesion_ts = None
        self._gracia_idle_hasta = None
        self._pregunta_hecha = False
        self._anclas_manuales = bool(apps)
        self.fotos = 0
        if self.cfg.camara.habilitada:
            self._podar_fotos()
        if texto:
            self.tarea = texto
        self._evento(
            TipoEvento.TAREA,
            motivo=f"sesion_inicio:{','.join(apps) or 'solo_inactividad'}",
        )
        if self.consola:
            linea_evento(
                f"SESIÓN ACTIVA: {texto or 'sin nombre'} · apps: {', '.join(apps) or '—'}"
                f" · reglas: {self.cfg.sesion.segundos_fuera_app}s fuera / "
                f"{self.cfg.sesion.segundos_inactivo}s inactivo · sin capturas",
                Fore.CYAN,
            )
        self.notifier.toast(
            "YourFocusGuard · sesión activa",
            f"Guardián de tarea activo: {texto or 'tarea'}. Te aviso si pasás "
            f"{self.cfg.sesion.segundos_fuera_app} s fuera de las apps o "
            f"{self.cfg.sesion.segundos_inactivo} s sin tocar nada.",
        )

    def _terminar_sesion(self, ahora: float, motivo: str) -> None:
        resumen = self.guardia.cerrar(ahora)
        # un episodio abierto se cierra con la sesión
        if self.off_since is not None:
            self.ladder.end(ahora)
            self.off_since = None
            self.clean_streak = 0
            self.silencio_fs = False
            self._llamados_episodio = 0
            self._frente_ya = False
            self._pregunta_hecha = False
        self._sesion_motivo = None
        self._gracia_idle_hasta = None
        self._ultimo_sesion_ts = None
        self._anclas_manuales = False
        self.estado = Estado.FOCO if self._hubo_veredicto_fuerte else Estado.EN_ESPERA
        self._evento(
            TipoEvento.TAREA,
            motivo=(
                f"sesion_fin:{motivo} dur_min:{resumen['duracion_min']:.0f} "
                f"en_app_min:{resumen['min_en_app']:.0f} alertas:{resumen['disparos']}"
            ),
        )
        if self.consola:
            linea_evento(
                f"sesión cerrada ({motivo}) · {resumen['min_en_app']:.0f} min en la tarea "
                f"de {resumen['duracion_min']:.0f} min · {resumen['disparos']} alertas",
                Fore.CYAN,
            )
        self.notifier.toast(
            "YourFocusGuard · sesión cerrada",
            f"Fin de la sesión ({motivo}): {resumen['min_en_app']:.0f} min en la tarea, "
            f"{resumen['disparos']} alertas"
            + (f", {self.fotos} fotos de verificación" if self.fotos else "")
            + ". Buen trabajo.",
        )

    # ------------------------------------------------------------------ #
    # Máquina de estados
    # ------------------------------------------------------------------ #

    def _actualizar_estado(self, ahora: float, veredicto: Verdict, snap: FrameSnapshot) -> None:
        umbral = self.cfg.cerebro.confianza_minima
        fuerte = veredicto.confianza >= umbral

        if fuerte:
            self._hubo_veredicto_fuerte = True
            if veredicto.desvio:
                self.clean_streak = 0
                if self.off_since is None:
                    # primera señal autoritaria: abre el episodio (t0 de la escalera)
                    self.off_since = ahora
                    self.ladder.begin(ahora)
                    self.silencio_fs = bool(
                        snap.fullscreen and self.cfg.alertas.silenciar_pantalla_completa
                    )
                    if self.consola:
                        if self.silencio_fs:
                            linea_evento(
                                f"señal de desvío ({veredicto.motivo}) · pantalla completa: modo silencioso",
                                Fore.YELLOW,
                            )
                        else:
                            linea_evento(
                                f"señal de desvío: {veredicto.motivo} "
                                f"({veredicto.confianza:.2f}, {veredicto.origen})",
                                Fore.YELLOW,
                            )
            else:
                if self.off_since is not None:
                    self.clean_streak += 1
                    if self.clean_streak >= 2:  # histéresis: 2 ciclos limpios
                        resumen = self.ladder.end(ahora)
                        self._evento(
                            TipoEvento.RETOMA,
                            estado=Estado.FOCO.value,
                            confianza=veredicto.confianza,
                            origen=veredicto.origen,
                        )
                        if self.consola and resumen:
                            linea_evento(
                                f"de vuelta al foco (+{resumen.duracion_min:.1f} min fuera)",
                                Fore.GREEN,
                            )
                        self.off_since = None
                        self.clean_streak = 0
                        self.silencio_fs = False
                        self._llamados_episodio = 0
                        self._frente_ya = False
                        self._pregunta_hecha = False
                else:
                    self.clean_streak = 0
        else:
            self.silencio_fs = self.silencio_fs and snap.fullscreen

        # estado efectivo del ciclo
        if self.off_since is not None:
            if self.ladder.en_cooldown(ahora):
                nuevo = Estado.COOLDOWN
            elif (ahora - self.off_since) >= self.cfg.alertas.desvio_sostenido_seg:
                nuevo = Estado.ESCALADA
            else:
                nuevo = Estado.FOCO  # sospecha sin confirmar: la escalera ya está abierta
        else:
            nuevo = Estado.FOCO if self._hubo_veredicto_fuerte else Estado.EN_ESPERA

        if nuevo == Estado.ESCALADA and self.estado != Estado.ESCALADA:
            self._evento(
                TipoEvento.DESVIO,
                confianza=veredicto.confianza,
                motivo=veredicto.motivo,
                accion_sugerida=veredicto.accion_sugerida,
                origen=veredicto.origen,
            )
        self.estado = nuevo

    def _escalar_si_toca(self, ahora: float, veredicto: Verdict) -> None:
        """Alimenta la escalera mientras el episodio de desvío siga abierto."""
        if self.off_since is None or self.silencio_fs:
            return
        minutos = (ahora - self.off_since) / 60.0
        alertas = self.ladder.tick(ahora, minutos, veredicto.motivo, self.tarea)
        for alerta in alertas:
            self._ejecutar_alerta(alerta, veredicto)
        if alertas:
            # v0.5.0: solo los avisos con peso cuentan como "llamado" para
            # traerte la app al frente. El aviso sutil (N1) es un empujón, no
            # un ultimátum; la pregunta contextual ya hizo de N0.
            self._llamados_episodio += sum(1 for a in alertas if a.nivel >= 2)
        # Se revisa en cada ciclo (no solo cuando suena una alerta): la
        # condición de "2 min de desvío" se cumple entre umbrales.
        self._quizas_traer_al_frente(ahora)

    def _ejecutar_alerta(self, alerta: Alerta, veredicto: Verdict) -> None:
        # v0.7.1: respetar niveles de aviso apagados por el usuario en settings
        niveles_apagados = {
            1: self.cfg.alertas.nivel_1_apagado,
            2: self.cfg.alertas.nivel_2_apagado,
            3: self.cfg.alertas.nivel_3_apagado,
            5: self.cfg.alertas.nivel_5_apagado,
        }
        if alerta.nivel in niveles_apagados and niveles_apagados[alerta.nivel]:
            return  # nivel desactivado en settings: no se ejecuta

        if alerta.nivel == 0:
            if self.consola:
                linea_evento(alerta.mensaje, Fore.YELLOW)
        elif alerta.nivel == 1:
            self.notifier.aviso(alerta.mensaje)
        elif alerta.nivel == 2:
            self.notifier.toast(alerta.titulo, alerta.mensaje)
            if self.consola:
                linea_evento(f"toast: {alerta.mensaje}", Fore.RED)
        elif alerta.nivel == 3:
            self.notifier.voz(alerta.texto_voz)
            if self.consola:
                linea_evento(f"voz: {alerta.texto_voz}", Fore.RED)
        if self.mascota is not None:
            self.mascota.al_alerta(
                alerta.nivel, alerta.mensaje or alerta.texto_voz
            )
        self._evento(
            TipoEvento.ALERTA,
            accion=alerta.accion.value,
            motivo=veredicto.motivo,
            confianza=veredicto.confianza,
            accion_sugerida=veredicto.accion_sugerida,
            origen=veredicto.origen,
        )

    # ------------------------------------------------------------------ #
    # Pausas
    # ------------------------------------------------------------------ #

    def _tick_en_pausa(self, ahora: float, motivo: str, detalle: str | None = None) -> dict:
        if self._pausa_actual != motivo:
            motivo_txt = f"{motivo} ({detalle})" if detalle else motivo
            self._evento(TipoEvento.PAUSA, estado=Estado.PAUSA.value, motivo=motivo_txt)
            if self.consola:
                linea_evento(f"en pausa — {motivo_txt}", Fore.CYAN)
            self._pausa_actual = motivo
            # una pausa cierra cualquier episodio de desvío abierto
            if self.off_since is not None:
                self.ladder.end(ahora)
                self.off_since = None
                self.clean_streak = 0
                self.silencio_fs = False
                self._llamados_episodio = 0
                self._frente_ya = False
                self._pregunta_hecha = False
        self.pom_ultimo_ts = ahora  # congela la acumulación de foco
        self.estado = Estado.PAUSA
        self._escribir_estado(ahora)
        return {"estado": self.estado.value, "pausa": self._pausa_actual}

    def _reanudar(self, ahora: float, motivo: str) -> None:
        self._pausa_actual = None
        self.estado = Estado.FOCO if self._hubo_veredicto_fuerte else Estado.EN_ESPERA
        self.pom_ultimo_ts = ahora
        if self.guardia.activa:
            self.guardia.reanudar(ahora)  # la pausa no cuenta como ausencia
            self._idle_verificado_en = None  # ni como congelamiento a verificar
        self._evento(
            TipoEvento.PAUSA, estado=self.estado.value, motivo=f"reanudacion:{motivo}"
        )
        if self.consola:
            linea_evento(f"reanudado ({motivo})", Fore.GREEN)

    def toggle_pausa_rapida(self) -> None:
        """Atajo global de pausa (Ctrl+Alt+F12 por defecto)."""
        ahora = self.reloj()
        if self.paused_until is not None:
            self.paused_until = None
            self._reanudar(ahora, "atajo")
        else:
            minutos = self.cfg.privacidad.pausa_rapida_min
            self.paused_until = ahora + minutos * 60
            self._tick_en_pausa(ahora, "manual", detalle=f"atajo, {minutos} min")

    # ------------------------------------------------------------------ #
    # Pomodoro
    # ------------------------------------------------------------------ #

    def _pomodoro_avanzar(self, ahora: float) -> None:
        if not self.cfg.pomodoro.habilitado or self.pom_fase != "foco":
            return
        if self.pom_ultimo_ts is not None:
            self.pom_acumulado += max(0.0, ahora - self.pom_ultimo_ts)
        self.pom_ultimo_ts = ahora

        if self.pom_acumulado >= self.cfg.pomodoro.foco_min * 60:
            self.pom_ciclos += 1
            larga = self.pom_ciclos % self.cfg.pomodoro.ciclos_para_larga == 0
            minutos = (
                self.cfg.pomodoro.pausa_larga_min if larga else self.cfg.pomodoro.pausa_min
            )
            self.pom_fase = "pausa_larga" if larga else "pausa"
            self.pom_fin_pausa = ahora + minutos * 60
            self.pom_acumulado = 0.0
            self.notifier.toast(
                "YourFocusGuard · Pomodoro",
                f"Ciclo {self.pom_ciclos} completado. Pausa de {minutos} min: respira.",
            )
            self._evento(
                TipoEvento.PAUSA,
                estado=Estado.PAUSA.value,
                motivo=f"pomodoro:ciclo_{self.pom_ciclos}",
            )

    def _fin_pausa_pomodoro(self, ahora: float) -> None:
        self.pom_fase = "foco"
        self.pom_acumulado = 0.0
        self.pom_fin_pausa = None
        self.pom_ultimo_ts = ahora
        self._pausa_actual = None
        if self.guardia.activa:
            self.guardia.reanudar(ahora)  # la pausa no cuenta como ausencia
            self._idle_verificado_en = None
        self.estado = Estado.FOCO if self._hubo_veredicto_fuerte else Estado.EN_ESPERA
        self.notifier.toast(
            "YourFocusGuard · Pomodoro",
            f"Fin de la pausa. Vuelta al foco (ciclo {self.pom_ciclos + 1}).",
        )
        self._evento(
            TipoEvento.PAUSA, estado=self.estado.value, motivo="fin_pausa_pomodoro"
        )

    # ------------------------------------------------------------------ #
    # Refuerzo positivo de enfoque continuo (micro-hitos para TDAH)
    # ------------------------------------------------------------------ #

    FRASES_REFUERZO = (
        "¡10 minutos de gran enfoque! ¡Excelente trabajo!",
        "¡Qué buena concentración llevas! Muse está feliz contigo.",
        "¡10 minutos impecables! Sigamos así, un paso a la vez.",
        "¡Foco total! ¡Lo estás haciendo increíble!",
        "¡Gran racha de enfoque! Respira hondo y sigamos con calma.",
    )

    def _comprobar_refuerzo_positivo(self, ahora: float) -> None:
        if not getattr(self.cfg.alertas, "refuerzo_positivo", True):
            self._foco_continuo_desde = None
            return

        intervalo_seg = getattr(self.cfg.alertas, "refuerzo_intervalo_min", 10) * 60

        if self.estado == Estado.FOCO and self.off_since is None and self._pausa_actual is None:
            if self._foco_continuo_desde is None:
                self._foco_continuo_desde = ahora
                self._ultimo_refuerzo_ts = ahora

            tiempo_foco = ahora - self._foco_continuo_desde

            # Sugerencia a los 30 min continuos de foco
            if tiempo_foco >= 30 * 60 and not self._foco_30min_sugerido:
                self._foco_30min_sugerido = True
                self._sugerir_pausa_30min(ahora)

            tiempo_desde_ultimo = ahora - (self._ultimo_refuerzo_ts or self._foco_continuo_desde)
            if tiempo_desde_ultimo >= intervalo_seg:
                self._ultimo_refuerzo_ts = ahora
                self._emitir_refuerzo_positivo(ahora, intervalo_min=int(intervalo_seg // 60))
        else:
            self._foco_continuo_desde = None
            self._ultimo_refuerzo_ts = None
            self._foco_30min_sugerido = False

    def _sugerir_pausa_30min(self, ahora: float) -> None:
        texto = "Llevas 30 min enfocado. ¿Tomamos 10 min de pausa o seguimos 15 min más?"
        if self.consola:
            linea_evento(f"⏳ Sugerencia 30 min: {texto}", Fore.YELLOW)

        self._evento(
            TipoEvento.ALERTA,
            estado=Estado.FOCO.value,
            motivo="30_min_foco_sugerencia_pausa",
            accion="pregunta_pausa",
        )

        try:
            from yourfocusguard.core.events import EVT_PET_REACTION, EVT_PET_SAY, publish
            publish(EVT_PET_REACTION, "waiting")
            publish(EVT_PET_SAY, {
                "texto": texto,
                "reaccion": "waiting",
                "duracion_ms": 12000,
                "opciones": ["Pausa 10m", "+15m"]
            })
        except Exception:
            pass

        if getattr(self.cfg.alertas, "tts_habilitado", True) and not getattr(self.cfg, "modo_privado", False):
            try:
                from yourfocusguard.actions import tts
                tts.speak(texto)
            except Exception:
                pass

    def _emitir_refuerzo_positivo(self, ahora: float, intervalo_min: int = 10) -> None:
        import random
        frase = random.choice(self.FRASES_REFUERZO)
        if self.consola:
            linea_evento(f"🌟 Refuerzo positivo: {frase}", Fore.GREEN)

        self._evento(
            TipoEvento.REFUERZO,
            estado=Estado.FOCO.value,
            motivo=f"{intervalo_min}_min_foco_continuo",
            accion="mascota_voz",
        )

        try:
            from yourfocusguard.core.events import EVT_PET_REACTION, EVT_PET_SAY, publish
            publish(EVT_PET_REACTION, "happy")
            publish(EVT_PET_SAY, {
                "texto": frase,
                "reaccion": "happy",
                "duracion_ms": 6000,
            })
        except Exception:
            pass

        if getattr(self.cfg.alertas, "tts_habilitado", True) and not getattr(self.cfg, "modo_privado", False):
            try:
                from yourfocusguard.actions import tts
                tts.speak(frase)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Control por archivo (pause/resume/stop/task/privado desde otra consola)
    # ------------------------------------------------------------------ #

    def _procesar_control(self, ahora: float) -> None:
        self._command_processor.procesar(ahora)

    # ------------------------------------------------------------------ #
    # Registro, latido y estado
    # ------------------------------------------------------------------ #

    def _evento(
        self,
        tipo: TipoEvento,
        estado: str | None = None,
        motivo: str | None = None,
        confianza: float | None = None,
        accion: str | None = None,
        accion_sugerida: str | None = None,
        origen: str | None = None,
    ) -> None:
        if not self.sesion_id:
            return
        try:
            self.db.insertar_evento(
                sesion_id=self.sesion_id,
                estado=estado or self.estado.value,
                tipo=tipo.value,
                motivo=motivo,
                app=self._last_app,
                titulo=self._last_title,
                confianza=confianza,
                accion=accion,
                accion_sugerida=accion_sugerida,
                origen=origen,
            )
        except Exception:
            log.exception("no se pudo registrar el evento %s", tipo.value)

    def _registrar_degradacion(self, tipo: str, motivo: str) -> None:
        """Callback del router y de la escalera (fallback, disyuntor, tope...)."""
        accion = "nada" if tipo == "alerta" else None
        self._evento(TipoEvento(tipo), motivo=motivo, accion=accion)

    def _latido(self, ahora: float, veredicto: Verdict) -> None:
        if ahora - self._last_heartbeat >= HEARTBEAT_SEG:
            self._last_heartbeat = ahora
            self._evento(
                TipoEvento.DETECCION,
                motivo=veredicto.motivo,
                confianza=veredicto.confianza,
                accion="nada",
                accion_sugerida=veredicto.accion_sugerida,
                origen=veredicto.origen,
            )

    def _escribir_estado(self, ahora: float, detenido: bool = False) -> None:
        pausa_hasta = self.paused_until or self.pom_fin_pausa
        data = {
            "version": __version__,
            "estado": "DETENIDO" if detenido else self._estado_visible(),
            "estado_interno": self.estado.value,
            "desde": _iso(self.off_since),
            "tarea": self.tarea,
            "cerebro": (
                self._ultimo_veredicto.origen if self._ultimo_veredicto else None
            ),
            "modo_privado": self.cfg.modo_privado,
            "pausa": {
                "motivo": self._pausa_actual,
                "hasta": _iso(pausa_hasta),
            },
            "pomodoro": {
                "fase": self.pom_fase,
                "ciclos": self.pom_ciclos,
                "foco_acumulado_min": round(self.pom_acumulado / 60, 1),
            },
            "sesion": {
                "activa": self.guardia.activa,
                "apps": self.guardia.apps,
                "fuera_hace_s": (
                    round(max(0.0, ahora - self.guardia.ultimo_visto))
                    if self.guardia.activa
                    else None
                ),
                "idle_s": (
                    round(self._sesion_idle) if self._sesion_idle is not None else None
                ),
                "fin": _iso(self.guardia.fin),
                "disparos": self.guardia.disparos,
                "fotos": self.fotos,
                "verificado_idle": self._idle_verificado_en is not None,
                "camara": self.camara is not None,
            },
            # v0.7.0 (Fase 3): modo máxima concentración y presencia física
            "concentracion": {
                "activo": self.concentracion.activo,
                "dominios": list(getattr(self.concentracion, "_hosts_lineas_anadidas", [])),
                "duracion_seg": round(self.concentracion.duracion_seg()),
            },
            "presencia": {
                "habilitada": self.cfg.presencia.habilitada,
                "disponible": self.presencia.disponible(),
                "en_silla": (
                    self.presencia.ultima().en_silla if self.presencia.ultima() else None
                ),
                "telefono_en_mano": (
                    self.presencia.ultima().telefono_en_mano if self.presencia.ultima() else None
                ),
            },
            # v0.3.0: para el panel y `status` (minutos consumidos hoy)
            "presupuestos": self.vigilante.resumen(),
            "avisos": {
                "modo": self.cfg.alertas.modo,
                "mascota": self.mascota is not None,
                "avatar": (
                    getattr(self.mascota, "nombre", "avatar")
                    if self.mascota is not None
                    else "ninguno"
                ),
            },
            "maquina": self.cfg.agente.maquina,
            "actualizado": _iso(ahora),
        }
        ruta = self.cfg.ruta_estado
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = ruta.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(ruta)
        except OSError:
            log.exception("no se pudo escribir state.json")
        # v0.3.0: la mascota refleja el estado visible (con reloj interno, no lanza)
        if self.mascota is not None:
            self.mascota.fijar_estado(self._estado_visible(), self.tarea)

    def _estado_visible(self) -> str:
        if self._pausa_actual:
            return Estado.PAUSA.value
        return self.estado.value

    def _descripcion_cerebro(self) -> str:
        if self.cfg.modo_privado:
            return "modo privado: solo Nivel B (heurística local)"
        if not self.router.nube_activa:
            return "Nivel B (heurística local, sin nube)"
        proveedor = self.cfg.cerebro.proveedor_nube
        modelo = (
            self.cfg.cerebro.modelo_gemini if proveedor == "gemini"
            else self.cfg.cerebro.modelo_openai
        )
        return f"Nivel A: {proveedor} · {modelo} (caída a Nivel B automática)"

    # ------------------------------------------------------------------ #
    # Atajo global de pausa (Windows)
    # ------------------------------------------------------------------ #

    def _activar_hotkey(self) -> None:
        if not self.hotkey or sys.platform != "win32":
            return
        try:
            import keyboard

            atajos = {
                self.cfg.privacidad.atajo_pausa: self.toggle_pausa_rapida,
                self.cfg.privacidad.atajo_sigo: self._pedir_sigo,
                self.cfg.privacidad.atajo_pausa_corta: self._pedir_pausa_corta,
            }
            for combinacion, accion in atajos.items():
                if combinacion:
                    keyboard.add_hotkey(combinacion, accion)
            self._hotkey_ok = True
            if self.consola:
                linea_evento(
                    f"atajos globales: {self.cfg.privacidad.atajo_pausa} pausa/reanuda · "
                    f"{self.cfg.privacidad.atajo_sigo} sigo aquí · "
                    f"{self.cfg.privacidad.atajo_pausa_corta} pausa corta "
                    f"({self.cfg.privacidad.pausa_corta_min} min)",
                    Fore.CYAN,
                )
        except Exception as exc:
            log.warning(
                "no se pudo registrar el atajo global (%s); usa `python run.py pause`",
                exc,
            )
