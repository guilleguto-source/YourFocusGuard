"""Carga y validación de la configuración TOML.

Capas (la última gana), según el blueprint (cap. 8, tabla 8):

    config/default.toml  ->  config/<perfil>.toml  ->  config/user.toml

Las claves están en español porque la configuración es un artefacto que edita
el usuario; el código que la consume está en inglés (decisión del sprint 1).
TOML se lee con ``tomllib`` de la librería estándar (tabla 9 del blueprint).
"""
from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CONFIG_DIR_DEFAULT = Path(__file__).resolve().parents[1] / "config"

PERFILES_VALIDOS = ("pc", "laptop")
PROVEEDORES_VALIDOS = ("gemini", "openai", "ninguno")
MODOS_AVISO = ("visual", "visual_sonoro", "completo")
PROVEEDORES_AVATAR = ("auto", "embed", "openpets", "tk", "ninguno")



# --------------------------------------------------------------------------- #
# Dataclasses por sección
# --------------------------------------------------------------------------- #

@dataclass
class AgenteCfg:
    perfil: str = "pc"
    maquina: str = "pc_diseno"
    prompt_id: str = "v1"


@dataclass
class CapturaCfg:
    # v0.4.0: la captura de pantalla sale del mapa (petición del usuario).
    # false = Modo Anclado: el agente se guía SOLO por primer plano + idle,
    # sin capturas, sin FIFO, sin nube. true = modo monitoreo clásico.
    habilitada: bool = False
    intervalo_seg: int = 15
    fifo_frames: int = 5
    monitor: int = 1
    escala_max_ancho: int = 1280
    calidad_jpeg: int = 80


@dataclass
class CerebroCfg:
    proveedor_nube: str = "gemini"
    analisis_nube_seg: int = 60
    imagenes_por_analisis: int = 2
    timeout_seg: int = 20
    temperatura: float = 0.0
    modelo_gemini: str = "gemini-2.0-flash"
    modelo_openai: str = "gpt-4o-mini"
    confianza_minima: float = 0.6
    presupuesto_diario_usd: float = 0.75
    coste_por_analisis_usd: float = 0.003
    cache_min_seg: int = 10
    disyuntor_fallos: int = 3
    disyuntor_descanso_min: int = 10


@dataclass
class HeuristicaCfg:
    apps_enfoque: list[str] = field(default_factory=list)
    titulos_enfoque: list[str] = field(default_factory=list)
    apps_distraccion: list[str] = field(default_factory=list)
    titulos_distraccion: list[str] = field(default_factory=list)
    apps_neutras: list[str] = field(default_factory=list)
    idle_ausencia_seg: int = 120


@dataclass
class AlertasCfg:
    desvio_sostenido_seg: int = 30
    mascota_seg: int = 20
    aviso_seg: int = 30
    toast_seg: int = 60
    voz_seg: int = 90
    enfriamiento_seg: int = 300
    tope_por_hora: int = 4
    tts_habilitado: bool = True
    tts_voz: str = ""
    tts_velocidad: int = 170
    toast_habilitado: bool = True
    silenciar_pantalla_completa: bool = True
    # v0.3.0: modos de aviso del panel (canales de la escalera)
    modo: str = "completo"            # visual | visual_sonoro | completo
    traer_al_frente_app: str = ""     # p. ej. "lightroom"; vacío = 1.ª app de la sesión
    traer_al_frente_tras: int = 2     # tras el 2.º (o 3.º) llamado
    # v0.5.0: el "traer al frente" espera a que el desvío lleve su tiempo y
    # cuenta solo avisos con peso (toast/voz), no el aviso sutil.
    minutos_antes_de_traer: float = 2.0
    # v0.7.1: niveles de aviso apagables por el usuario en settings
    nivel_1_apagado: bool = False   # mascota (N0)
    nivel_2_apagado: bool = False   # aviso sutil (N1)
    nivel_3_apagado: bool = False   # toast (N2)
    nivel_5_apagado: bool = False   # voz (N3) / cooldown
    # v0.8.2: refuerzo positivo de enfoque continuo (celebrar cada N minutos)
    refuerzo_positivo: bool = True
    refuerzo_intervalo_min: int = 10


@dataclass
class ProhibicionCfg:
    """Una prohibición: patrón + presupuesto diario + bloqueo activo.

    ``excepciones`` (v0.4.0): patrones de título que NO cuentan — p. ej.
    "youtube" prohibido pero "youtube music" permitido (música sí, vídeos no).
    """

    patron: str = ""                # regex simple sobre proceso o título
    limite_min_dia: int = 60        # minutos de primer plano permitidos al día
    bloqueo_activo: bool = False    # al agotarse: minimizar la app cada vez que vuelve
    excepciones: list[str] = field(default_factory=list)  # títulos que no cuentan

    def __post_init__(self) -> None:
        self.patron = str(self.patron or "").strip().lower()
        self.limite_min_dia = int(self.limite_min_dia)
        self.bloqueo_activo = bool(self.bloqueo_activo)
        self.excepciones = [
            str(x).strip().lower() for x in (self.excepciones or []) if str(x).strip()
        ][:8]

    def firma(self) -> tuple:
        return (self.patron, self.limite_min_dia, self.bloqueo_activo, tuple(self.excepciones))


@dataclass
class ProhibicionesCfg:
    """Sección [prohibiciones]: presupuestos diarios por app/sitio (v0.3.0)."""

    lista: list[ProhibicionCfg] = field(default_factory=list)

    def __post_init__(self) -> None:
        # tomllib entrega array-of-inline-tables como list[dict]: normalizar
        salida: list[ProhibicionCfg] = []
        for entrada in self.lista or []:
            if isinstance(entrada, ProhibicionCfg):
                salida.append(entrada)
            elif isinstance(entrada, dict):
                salida.append(ProhibicionCfg(**entrada))
        self.lista = salida

    def firma(self) -> tuple:
        return tuple(e.firma() for e in self.lista)


@dataclass
class MascotaCfg:
    """Sección [mascota]: la guardiana de escritorio (v0.3.0)."""

    visible: bool = True
    tema: str = "clasico"           #TEMAS en mascota.py: clasico | oscuro | calido
    posicion: str = "inferior_derecha"  # inferior_derecha | inferior_izquierda
    ancho: int = 150                # tamaño del lienzo en px


@dataclass
class AvatarCfg:
    """Sección [avatar] (v0.6.0): qué cara pone el asistente.

    auto      -> OpenPets si está abierto y accesible; si no, la mascota tkinter
    openpets  -> solo OpenPets (sin fallback)
    tk        -> solo la mascota integrada
    ninguno   -> sin cara (consola, toasts y voz)
    """

    proveedor: str = "auto"         # auto | embed | openpets | tk | ninguno
    mascota: str = "einstein"       # null-wisp | einstein | bitty | glitchcat | luffy-gear-5 | meowbot | pixel-terminal | shadow-kit | wukong
    frases: bool = True             # burbujas de texto en el avatar


@dataclass
class FlujoGrupoCfg:
    nombre: str = ""
    apps: list[str] = field(default_factory=list)
    apps_relacionadas: list[str] = field(default_factory=list)
    tolerancia_min: float = 2.0
    mensaje_aviso: str = ""


@dataclass
class FlujosCfg:
    """Sección [flujos]: grupos de trabajo y apps relacionadas (v0.8.0)."""

    habilitado: bool = True
    aprendizaje: bool = True
    umbral_descubrimiento_min: int = 2
    grupo: list[dict[str, Any]] = field(default_factory=list)



@dataclass
class ConcentracionCfg:
    """Sección [concentracion]: modo máxima concentración (v0.7.0, Fase 3).

    Cuando se activa (sesión de máxima concentración), el agente no solo avisa:
    actúa. Puede reescribir el archivo hosts de Windows para bloquear dominios
    distractores (YouTube, Instagram, TikTok…), silenciar el audio del sistema
    y minimizar procesos bloqueados cada vez que vuelvan al frente. Todo se
    deshace al cerrar la sesión o al desactivar el modo.
    """

    habilitado: bool = False          # modo máxima concentración on/off
    bloquear_hosts: bool = True       # reescribir C:\Windows\System32\drivers\etc\hosts
    silenciar_audio: bool = True      # mute del dispositivo de salida por defecto
    dominios: list[str] = field(default_factory=list)  # dominios a bloquear (sin https://)
    apps_bloqueadas: list[str] = field(default_factory=list)  # procesos a minimizar al frente
    restaurar_al_salir: bool = True   # deshacer hosts/audio al cerrar la sesión
    duracion_min: int = 0             # 0 = hasta próximo reinicio; 30/60/120/300 presets


@dataclass
class PresenciaCfg:
    """Sección [presencia]: detección de usuario y teléfono (v0.7.0, Fase 3).

    MediaPipe bajo demanda: detecta si hay una persona frente a la cámara
    (está en la silla) y si sostiene un teléfono en la mano. Opt-in por
    privacidad: la cámara solo se abre para un frame puntual, nunca de forma
    continua. Requiere opencv-python-headless y mediapipe (no están en
    requirements.txt por defecto; se instalan a mano si se usan).
    """

    habilitada: bool = False          # opt-in: false = sin detección de presencia
    indice_camara: int = 0            # índice de la webcam a usar
    intervalo_seg: int = 30           # cada cuántos segundos comprobar presencia
    ausente_para_pausar_seg: int = 120  # sin rostro detectado durante N s -> pausa sola
    telefono_en_mano_seg: int = 10    # teléfono detectado durante N s -> aviso de concentración


@dataclass
class PanelCfg:
    """Sección [panel]: panel web local de configuración (v0.3.0)."""

    activo: bool = True
    puerto: int = 8756              # solo 127.0.0.1, nunca la red
    abrir_navegador: bool = True    # abrir el panel al arrancar el agente


@dataclass
class PomodoroCfg:
    habilitado: bool = True
    foco_min: int = 25
    pausa_min: int = 5
    pausa_larga_min: int = 15
    ciclos_para_larga: int = 4


@dataclass
class CamaraCfg:
    """Webcam de verificación bajo demanda (v0.2.1, propuesta del usuario).

    Opt-in por privacidad: la cámara solo se abre para capturar UN frame
    cuando el motor lo pide (N segundos de inactividad en una sesión, o una
    regla R1/R2 disparada). Nunca queda encendida de forma continua.
    """

    habilitada: bool = False     # opt-in: false = el agente no toca la webcam
    indice: int = 0              # 0 = webcam por defecto; cambiar si hay varias
    ancho_max: int = 640         # minimización: se reescala antes de guardar
    calidad_jpeg: int = 80
    preframes: int = 6           # frames de estabilización antes de capturar
    foto_en_disparo: bool = True  # foto de webcam además de la captura, al disparar R1/R2
    guardar_fotos: bool = True   # false = la foto vive solo en RAM y se descarta
    retencion_dias: int = 7      # poda de la carpeta data/fotos


@dataclass
class SesionCfg:
    """Modo sesión: guardián de tarea por predicados, sin capturas (v0.2.0).

    ``apps`` puede dejarse vacío aquí (se declara por CLI con ``session``
    start --apps ...``) o fijarse en user.toml para una rutina diaria.
    """

    apps: list[str] = field(default_factory=list)
    apps_auxiliares: list[str] = field(default_factory=list)
    segundos_fuera_app: int = 60
    segundos_inactivo: int = 60
    intervalo_sondeo: int = 5
    capturar_al_disparar: bool = False  # v0.4.0: capturas fuera del mapa por defecto
    verificar_con_camara_seg: int = 20  # 0 = desactiva la foto de verificación
    # v0.5.0: si no estás en la silla (pantalla bloqueada, suspensión o idle
    # largo) el guardián se pausa SOLO en vez de reclamarte. 0 = desactivado.
    ausencia_seg: int = 300
    # v0.5.0: tu petición literal —"que Lightroom esté AL FRENTE"—. false
    # mantiene el comportamiento tolerante: la app visible en el otro monitor
    # cuenta como presente (útil para consultar referencias).
    exigir_primer_plano: bool = False
    # v0.5.0: además, exigir que la ventana al frente esté en ESTE monitor
    # (1..N). 0 = cualquiera. Útil si trabajas siempre en el segundo.
    monitor_objetivo: int = 0


@dataclass
class PrivacidadCfg:
    apps_excluidas: list[str] = field(default_factory=list)
    titulos_excluidos: list[str] = field(default_factory=list)
    atajo_pausa: str = "ctrl+alt+f12"
    pausa_rapida_min: int = 15
    # v0.5.0: canal de respuesta a la pregunta contextual ("¿qué haces?").
    # El asistente pregunta y tú contestas sin tocar el teclado del agente.
    atajo_sigo: str = "ctrl+alt+f11"       # "estoy en la tarea": cierra el aviso
    atajo_pausa_corta: str = "ctrl+alt+f10"  # pausa corta a pedido
    pausa_corta_min: int = 10


@dataclass
class DatosCfg:
    carpeta: str = "./data"
    retencion_dias: int = 180


@dataclass
class RegistroCfg:
    nivel: str = "INFO"


@dataclass
class VozCfg:
    """Configuración de voz y tiempos de escucha (v0.8.3 O-03)."""

    segundos_escucha: float = 8.0
    segundos_n3: float = 7.0


@dataclass
class NotasCfg:
    """Configuración del buzón de captura rápida (Brain Dump) para Logseq o Markdown."""

    habilitado: bool = True
    carpeta_diario: str = ""
    archivo_inbox_respaldo: str = "./data/inbox_tdah.md"
    formato_todo: bool = True


@dataclass
class RutinasCfg:
    """Configuración de hábitos y recordatorios periódicos (v0.8.3 Fase 3)."""

    habilitado: bool = True
    pausa_activa_cada_min: int = 50
    pausa_activa_mensaje: str = "Llevas 50 minutos concentrado. Estira la espalda y toma un vaso de agua."
    ejercicio_hora: str = ""
    ejercicio_mensaje: str = "Momento de cerrar pantallas y hacer ejercicio."


@dataclass
class VikunjaCfg:
    """Configuración de integración con Vikunja (v0.8.3 Fase 4)."""

    habilitado: bool = False
    url: str = ""
    token: str = ""
    proyecto_defecto_id: int = 1


@dataclass
class MusicaCfg:
    """Configuración del controlador de música y ruido de foco (v0.8.3 Fase 4)."""

    habilitado: bool = True
    volumen: float = 0.5
    url_stream: str = ""


@dataclass
class Config:
    """Configuración completa del agente, ya resuelta y validada."""

    agente: AgenteCfg
    captura: CapturaCfg
    cerebro: CerebroCfg
    heuristica: HeuristicaCfg
    alertas: AlertasCfg
    pomodoro: PomodoroCfg
    sesion: SesionCfg
    camara: CamaraCfg
    privacidad: PrivacidadCfg
    prohibiciones: ProhibicionesCfg
    mascota: MascotaCfg
    avatar: AvatarCfg
    panel: PanelCfg
    concentracion: ConcentracionCfg
    presencia: PresenciaCfg
    flujos: FlujosCfg
    datos: DatosCfg
    registro: RegistroCfg
    voz: VozCfg = field(default_factory=VozCfg)
    notas: NotasCfg = field(default_factory=NotasCfg)
    rutinas: RutinasCfg = field(default_factory=RutinasCfg)
    vikunja: VikunjaCfg = field(default_factory=VikunjaCfg)
    musica: MusicaCfg = field(default_factory=MusicaCfg)


    # Rutas derivadas (absolutas) que usa todo el sistema.
    carpeta_datos: Path = field(init=False)
    ruta_db: Path = field(init=False)
    ruta_log: Path = field(init=False)
    ruta_estado: Path = field(init=False)
    ruta_control: Path = field(init=False)
    ruta_fotos: Path = field(init=False)
    modo_privado: bool = False  # se activa con --privado o control "privado"

    # Huella del user.toml para la recarga en vivo (panel -> agente).
    _huella_user: tuple | None = field(default=None, init=False, repr=False)
    _config_dir: Path | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        base = Path(self.datos.carpeta).expanduser()
        if not base.is_absolute():
            base = Path.cwd() / base
        self.carpeta_datos = base
        self.ruta_db = base / "yourfocusguard.db"
        self.ruta_log = base / "logs" / "agente.log"
        self.ruta_estado = base / "state.json"
        self.ruta_control = base / "control.json"
        self.ruta_fotos = base / "fotos"

    def refrescar_si_cambia(self) -> bool:
        """Recarga user.toml si cambió, mutando las secciones EN EL MISMO objeto.

        Así el motor, la escalera, el guardián de sesión y el vigilante ven
        los nuevos valores al siguiente ciclo sin reiniciar (lo pide el panel
        web). Devuelve True si aplicó una recarga. Ante un user.toml inválido
        se queda con lo anterior y avisa (nunca lanza: el agente no muere).
        """
        carpeta = self._config_dir or CONFIG_DIR_DEFAULT
        ruta = carpeta / "user.toml"
        huella = _huella_toml(ruta)
        if huella == self._huella_user:
            return False
        self._huella_user = huella
        try:
            nueva = load_config(
                perfil=self.agente.perfil,
                config_dir=carpeta,
                datos_carpeta=str(self.datos.carpeta),
                modo_privado=self.modo_privado,
            )
        except Exception as exc:
            log.warning("user.toml inválido, sigo con la configuración anterior: %s", exc)
            return False
        for nombre in _SECCIONES_RECARGABLES:
            getattr(self, nombre).__dict__.update(getattr(nueva, nombre).__dict__)
        log.info("configuración recargada en vivo desde user.toml")
        return True


# --------------------------------------------------------------------------- #
# Carga por capas
# --------------------------------------------------------------------------- #

_SECCIONES = {
    "agente": AgenteCfg,
    "captura": CapturaCfg,
    "cerebro": CerebroCfg,
    "heuristica": HeuristicaCfg,
    "alertas": AlertasCfg,
    "pomodoro": PomodoroCfg,
    "sesion": SesionCfg,
    "camara": CamaraCfg,
    "privacidad": PrivacidadCfg,
    "prohibiciones": ProhibicionesCfg,
    "mascota": MascotaCfg,
    "avatar": AvatarCfg,
    "panel": PanelCfg,
    "concentracion": ConcentracionCfg,
    "presencia": PresenciaCfg,
    "flujos": FlujosCfg,
    "datos": DatosCfg,
    "registro": RegistroCfg,
    "voz": VozCfg,
    "notas": NotasCfg,
    "rutinas": RutinasCfg,
    "vikunja": VikunjaCfg,
    "musica": MusicaCfg,
}



def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Fusión profunda: overlay pisa base, sin mutar ninguno de los dos."""
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _build_seccion(nombre: str, datos: dict[str, Any]) -> Any:
    """Construye la dataclass de una sección avisando de claves desconocidas."""
    cls = _SECCIONES[nombre]
    conocidas = {f.name for f in fields(cls)}
    for clave in datos:
        if clave not in conocidas:
            log.warning("Config: clave desconocida [%s] %s (se ignora)", nombre, clave)
    filtrados = {k: v for k, v in datos.items() if k in conocidas}
    return cls(**filtrados)


def _validar(cfg: Config) -> None:
    """Validaciones de sentido común con mensajes en español."""
    c = cfg.cerebro
    if c.proveedor_nube not in PROVEEDORES_VALIDOS:
        raise ValueError(
            f"cerebro.proveedor_nube inválido: {c.proveedor_nube!r}; "
            f"usa uno de {PROVEEDORES_VALIDOS}"
        )
    if cfg.captura.intervalo_seg < 5:
        raise ValueError("captura.intervalo_seg debe ser >= 5 (blueprint: 15 s)")
    if not 2 <= cfg.captura.fifo_frames <= 10:
        raise ValueError("captura.fifo_frames debe estar entre 2 y 10")
    if not 1 <= cfg.captura.monitor <= 16:
        log.warning("captura.monitor=%s: no parece un monitor real", cfg.captura.monitor)
    if not 0.0 <= c.confianza_minima <= 1.0:
        raise ValueError("cerebro.confianza_minima debe estar entre 0.0 y 1.0")
    a = cfg.alertas
    if a.modo not in MODOS_AVISO:
        raise ValueError(
            f"alertas.modo inválido: {a.modo!r}; usa uno de {MODOS_AVISO}"
        )
    if not 1 <= a.traer_al_frente_tras <= 5:
        log.warning("alertas.traer_al_frente_tras=%s fuera de 1-5", a.traer_al_frente_tras)
    if not 20 <= a.desvio_sostenido_seg <= 300:
        log.warning(
            "alertas.desvio_sostenido_seg=%s fuera del rango 20-300; "
            "la tabla 5 del blueprint recomienda 20-60",
            a.desvio_sostenido_seg,
        )
    if a.desvio_sostenido_seg < 10 or a.desvio_sostenido_seg > 600:
        raise ValueError("alertas.desvio_sostenido_seg debe quedar entre 10 y 600")
    if not (a.mascota_seg < a.aviso_seg < a.toast_seg < a.voz_seg):
        log.warning("alertas: la escalera debe ser creciente (20 < 30 < 60 < 90 por defecto)")
    if cfg.agente.maquina not in ("pc_diseno", "laptop"):
        log.warning("agente.maquina=%r no es 'pc_diseno' ni 'laptop'", cfg.agente.maquina)
    s = cfg.sesion
    if s.segundos_fuera_app < 10 or s.segundos_inactivo < 10:
        log.warning(
            "[sesion] umbrales < 10 s son muy agresivos (falsos positivos con "
            "cargas, renders y pausas de reflexión)"
        )
    if not 2 <= s.intervalo_sondeo <= 60:
        log.warning("[sesion] intervalo_sondeo=%s fuera del rango razonable 2-60", s.intervalo_sondeo)
    if s.verificar_con_camara_seg < 0:
        raise ValueError("sesion.verificar_con_camara_seg no puede ser negativo; 0 = desactivado")
    if s.ausencia_seg < 0:
        raise ValueError("sesion.ausencia_seg no puede ser negativo; 0 = desactivado")
    if 0 < s.ausencia_seg < 60:
        log.warning(
            "[sesion] ausencia_seg=%s: menos de 1 min pausaría la sesión por "
            "cualquier pausa para pensar", s.ausencia_seg,
        )
    if a.minutos_antes_de_traer < 0:
        raise ValueError("alertas.minutos_antes_de_traer no puede ser negativo")
    if a.traer_al_frente_tras >= 2 and a.minutos_antes_de_traer < 1:
        log.warning(
            "[alertas] minutos_antes_de_traer=%.1f: la app saltará al frente "
            "casi junto con el primer aviso", a.minutos_antes_de_traer,
        )
    cm = cfg.camara
    if cm.indice < 0:
        raise ValueError("camara.indice no puede ser negativo")
    if cm.habilitada:
        if cm.ancho_max < 320:
            log.warning(
                "[camara] ancho_max=%s: fotos de más de 320 px contradicen la "
                "minimización de datos (cap. 7)", cm.ancho_max,
            )
        if cm.retencion_dias < 1:
            log.warning("[camara] retencion_dias < 1: las fotos se podan al día siguiente")
        if cm.preframes < 1:
            log.warning("[camara] preframes < 1: la primera foto puede salir a oscuras")

    # --- v0.3.0: prohibiciones, mascota y panel ---
    if len(cfg.prohibiciones.lista) > 12:
        raise ValueError("[prohibiciones] máximo 12 entradas (el panel también lo limita)")
    for entrada in cfg.prohibiciones.lista:
        if not entrada.patron:
            raise ValueError("[prohibiciones] hay un patrón vacío")
        if len(entrada.patron) > 64:
            raise ValueError(f"[prohibiciones] patrón demasiado largo: {entrada.patron!r}")
        if len(entrada.excepciones) > 8:
            raise ValueError(
                f"[prohibiciones] {entrada.patron!r}: máximo 8 excepciones"
            )
        for exc in entrada.excepciones:
            if len(exc) > 64:
                raise ValueError(
                    f"[prohibiciones] excepción demasiado larga en "
                    f"{entrada.patron!r}: {exc!r}"
                )
        if not 5 <= entrada.limite_min_dia <= 480:
            raise ValueError(
                f"[prohibiciones] limite_min_dia debe estar entre 5 y 480: "
                f"{entrada.limite_min_dia} ({entrada.patron!r})"
            )
    if not cfg.mascota.tema:
        log.warning("[mascota] tema vacío: se usará 'clasico'")
    if cfg.mascota.ancho < 80 or cfg.mascota.ancho > 400:
        log.warning("[mascota] ancho=%s fuera de 80-400 px", cfg.mascota.ancho)
    if cfg.avatar.proveedor not in PROVEEDORES_AVATAR:
        raise ValueError(
            f"avatar.proveedor inválido: {cfg.avatar.proveedor!r}; "
            f"usa uno de {PROVEEDORES_AVATAR}"
        )
    if cfg.avatar.proveedor in ("openpets", "auto") and not cfg.mascota.visible:
        log.info(
            "[avatar] proveedor=%s con la mascota oculta: si OpenPets no está "
            "abierto, el asistente se queda sin cara",
            cfg.avatar.proveedor,
        )
    if not 1024 <= cfg.panel.puerto <= 65535:
        raise ValueError(f"[panel] puerto inválido: {cfg.panel.puerto}")


def load_config(
    perfil: str = "pc",
    config_dir: Path | None = None,
    datos_carpeta: str | None = None,
    modo_privado: bool = False,
) -> Config:
    """Carga default.toml + <perfil>.toml + user.toml y valida el resultado.

    ``datos_carpeta`` permite redirigir la carpeta de datos (lo usan los tests
    y también quien quiera llevar la base en otra ruta).
    """
    if perfil not in PERFILES_VALIDOS:
        raise ValueError(f"perfil inválido: {perfil!r}; usa {PERFILES_VALIDOS}")

    config_dir = Path(config_dir) if config_dir else CONFIG_DIR_DEFAULT
    capas = [
        _read_toml(config_dir / "default.toml"),
        _read_toml(config_dir / f"{perfil}.toml"),
        _read_toml(config_dir / "user.toml"),  # opcional, gitignored
    ]
    combinado: dict[str, Any] = {}
    for capa in capas:
        combinado = _deep_merge(combinado, capa)

    desconocidas = set(combinado) - set(_SECCIONES)
    if desconocidas:
        raise ValueError(
            f"secciones desconocidas en la configuración: {sorted(desconocidas)}; "
            f"válidas: {sorted(_SECCIONES)}"
        )

    secciones = {
        nombre: _build_seccion(nombre, combinado.get(nombre, {}))
        for nombre in _SECCIONES
    }
    cfg = Config(**secciones)
    cfg.agente.perfil = perfil

    if datos_carpeta:
        cfg.datos.carpeta = datos_carpeta
        cfg.__post_init__()  # recalcular rutas derivadas

    cfg.modo_privado = modo_privado
    _validar(cfg)
    cfg._config_dir = Path(config_dir)
    cfg._huella_user = _huella_toml(ruta_user_de(config_dir, perfil))
    return cfg


def ruta_user_de(config_dir: Path, perfil: str) -> Path:
    """Ruta del user.toml del perfil (existe o no)."""
    return Path(config_dir) / "user.toml"


def _huella_toml(ruta: Path) -> tuple | None:
    """(mtime_ns, size) del archivo; None si no existe."""
    try:
        st = ruta.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


_SECCIONES_RECARGABLES = (
    "agente", "captura", "cerebro", "heuristica", "alertas", "pomodoro",
    "sesion", "camara", "privacidad", "prohibiciones", "mascota", "avatar",
    "panel", "concentracion", "presencia", "flujos", "registro", "voz", "notas", "rutinas",
    "vikunja", "musica",
)


def serializar_toml(datos: dict) -> str:
    """Escritor TOML mínimo para user.toml (stdlib, sin tomli-w).

    Soporta: secciones anidadas (1 nivel), str/int/float/bool, list[str] y
    list[dict] (arrays de tablas inline, como [prohibiciones].lista).
    """
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def valor(v) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            return f'"{esc(v)}"'
        if isinstance(v, float):
            return repr(round(v, 6))
        if isinstance(v, int):
            return str(v)
        if isinstance(v, list):
            if not v:
                return "[]"
            if all(isinstance(x, str) for x in v):
                cuerpo = ",\n  ".join(valor(x) for x in v)
                return f"[\n  {cuerpo},\n]"
            if all(isinstance(x, dict) for x in v):
                tablas = []
                for x in v:
                    pares = ", ".join(f"{k} = {valor(iv)}" for k, iv in x.items())
                    tablas.append(f"{{ {pares} }}")
                cuerpo = ",\n  ".join(tablas)
                return f"[\n  {cuerpo},\n]"
            raise ValueError(f"lista mixta no soportada: {v!r}")
        raise ValueError(f"valor TOML no soportado: {v!r}")

    lineas: list[str] = []
    for clave, v in datos.items():
        if isinstance(v, dict):
            continue  # secciones al final
        lineas.append(f"{clave} = {valor(v)}")
    for clave, v in datos.items():
        if not isinstance(v, dict):
            continue
        if lineas:
            lineas.append("")
        lineas.append(f"[{clave}]")
        for subclave, sv in v.items():
            if isinstance(sv, dict):
                continue  # máximo 1 nivel de anidado en user.toml
            lineas.append(f"{subclave} = {valor(sv)}")
    return "\n".join(lineas) + "\n"


CABECERA_USER_TOML = """# ===========================================================================
# YourFocusGuard — tus ajustes (capa user.toml)
#
# Generado por el Panel del Guardián; edítalo a mano si prefieres.
# Pisa a default.toml y al perfil; la última capa gana. No se sube a git.
# ===========================================================================
"""


def escribir_user_toml(
    ruta: Path,
    overlay: dict,
    existente: dict | None = None,
) -> dict:
    """Fusiona ``overlay`` sobre el user.toml actual y lo escribe atómicamente.

    Devuelve el dict fusionado (útil para tests). """
    if existente is None:
        try:
            with Path(ruta).open("rb") as fh:
                existente = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            existente = {}
    fusion = _deep_merge(existente, overlay)
    texto = CABECERA_USER_TOML + serializar_toml(fusion)
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)
    return fusion
