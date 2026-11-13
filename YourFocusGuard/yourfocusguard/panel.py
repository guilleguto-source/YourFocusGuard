"""Panel del Guardián: configuración web local (v0.3.0).

Servidor HTTP en 127.0.0.1 (nunca la red) con la página de ajustes del
agente: frecuencia de monitoreo, pantalla principal, tiempos de
intervención, modos de aviso, prohibiciones con presupuesto diario y la
mascota. Lo pidió el usuario: "un lugar para configurar la frecuencia del
monitoreo... que permita configurar diversas cosas".

    python run.py panel              # panel solo (funciona sin agente)
    python run.py start              # agente + panel (Ctrl+C detiene ambos)

El panel NO duplica ajustes: escribe la capa config/user.toml y el agente
la recarga en vivo al ciclo siguiente (<= 15 s). Los botones de acción
usan el mismo control.json que la consola. Sin dependencias nuevas:
http.server de la librería estándar.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from yourfocusguard import __version__
from yourfocusguard.config import Config, load_config, escribir_user_toml
from yourfocusguard.storage.db import EventDB

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "panel_static"
TEMAS_MASCOTA = ("clasico", "oscuro", "calido")
MODOS = ("visual", "visual_sonoro", "completo")
MAX_PROHIBICIONES = 12
SEGS_VIVO = 120  # un state.json más viejo que esto = agente detenido

# Estado compartido en memoria para la mascota embebida
_PET_LOCK = threading.Lock()
_PET_STATE = {
    "mascota": "null-wisp",
    "reaccion": "idle",
    "burbuja": {"texto": "", "opciones": [], "duracion": 4000},
    "respuestas": [],
}


def pet_listar_disponibles() -> list[dict[str, str]]:
    """Lista todas las mascotas encontradas en panel_static/pets/."""
    pets_dir = STATIC_DIR / "pets"
    if not pets_dir.is_dir():
        return [{"id": "null-wisp", "nombre": "Null Wisp"}]
    resultado = []
    for d in sorted(pets_dir.iterdir()):
        if d.is_dir():
            pet_id = d.name
            nombre = pet_id.replace("-", " ").title()
            meta_json = d / "pet.json"
            if meta_json.is_file():
                try:
                    meta = json.loads(meta_json.read_text(encoding="utf-8"))
                    nombre = meta.get("displayName") or nombre
                except Exception:
                    pass
            resultado.append({"id": pet_id, "nombre": nombre})
    return resultado


def pet_estado_actual() -> dict:

    with _PET_LOCK:
        return dict(_PET_STATE)


def pet_fijar_reaccion(reaccion: str) -> None:
    with _PET_LOCK:
        _PET_STATE["reaccion"] = str(reaccion or "idle").lower()


def pet_fijar_mascota(nombre: str) -> None:
    with _PET_LOCK:
        _PET_STATE["mascota"] = str(nombre or "null-wisp").strip()


def pet_decir(texto: str, reaccion: str | None = None, opciones: list[str] | None = None, duracion_ms: int = 4000, auto_confirmar_seg: int = 0) -> None:
    with _PET_LOCK:
        if reaccion:
            _PET_STATE["reaccion"] = str(reaccion).lower()
        _PET_STATE["burbuja"] = {
            "texto": str(texto or "").strip(),
            "opciones": list(opciones or []),
            "duracion": int(duracion_ms),
            "auto_confirmar_seg": int(auto_confirmar_seg),
        }


def pet_registrar_respuesta(respuesta: str) -> None:
    with _PET_LOCK:
        _PET_STATE["respuestas"].append(str(respuesta))


# Conectar eventos en memoria para desacoplamiento arquitectónico
from yourfocusguard.core.events import (
    EVT_PET_REACTION,
    EVT_PET_SAY,
    EVT_PET_SET,
    EVT_USER_VOICE_RESPONSE,
    subscribe,
)

subscribe(
    EVT_PET_SAY,
    lambda d: pet_decir(
        d.get("texto", ""),
        reaccion=d.get("reaccion"),
        opciones=d.get("opciones"),
        duracion_ms=d.get("duracion_ms", 4000),
        auto_confirmar_seg=d.get("auto_confirmar_seg", 0),
    )
    if isinstance(d, dict)
    else pet_decir(str(d)),
)
subscribe(EVT_PET_REACTION, lambda r: pet_fijar_reaccion(str(r)))
subscribe(EVT_PET_SET, lambda m: pet_fijar_mascota(str(m)))
subscribe(EVT_USER_VOICE_RESPONSE, lambda r: pet_registrar_respuesta(str(r)))



def pet_consumir_respuestas() -> list[str]:
    with _PET_LOCK:
        res = list(_PET_STATE["respuestas"])
        _PET_STATE["respuestas"].clear()
        return res



# --------------------------------------------------------------------------- #
# Payload de estado (función pura: la usan el handler y los tests)
# --------------------------------------------------------------------------- #

def _leer_state(cfg: Config) -> dict | None:
    try:
        return json.loads(cfg.ruta_estado.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _agente_vivo(cfg: Config, state: dict | None) -> bool:
    if not state or state.get("estado") == "DETENIDO":
        return False
    try:
        from datetime import datetime

        actualizado = datetime.fromisoformat(state["actualizado"])
        return (datetime.now().astimezone() - actualizado).total_seconds() < SEGS_VIVO
    except (KeyError, ValueError):
        return False


def _config_fresca(cfg: Config) -> Config:
    """Configuración releída de disco (el panel siempre muestra lo último)."""
    try:
        return load_config(
            perfil=cfg.agente.perfil,
            config_dir=cfg._config_dir,
            datos_carpeta=str(cfg.datos.carpeta),
        )
    except Exception:
        return cfg


def payload_estado(cfg: Config) -> dict:
    state = _leer_state(cfg)
    fresca = _config_fresca(cfg)

    presupuestos: dict[str, int] = {}
    nube_usd = 0.0
    if cfg.ruta_db.exists():
        try:
            db = EventDB(cfg.ruta_db)
            presupuestos = db.presupuestos_hoy()
            nube_usd = db.presupuesto_hoy()
            db.cerrar()
        except Exception:
            log.exception("no se pudo leer la base para el panel")

    from yourfocusguard.capture import window_info

    prohibiciones = [
        {
            "patron": e.patron,
            "limite_min": e.limite_min_dia,
            "bloqueo_activo": e.bloqueo_activo,
            "excepciones": list(e.excepciones),
            "usado_min": round(presupuestos.get(e.patron, 0) / 60.0, 1),
            "excedido": e.limite_min_dia * 60 <= presupuestos.get(e.patron, 0),
        }
        for e in fresca.prohibiciones.lista
    ]
    ses = (state or {}).get("sesion") or {}
    return {
        "version": __version__,
        "corriendo": _agente_vivo(cfg, state),
        "estado": state,
        "sesion_activa": bool(ses.get("activa")),
        "nube_usd_hoy": round(nube_usd, 3),
        "monitores": window_info.listar_monitores(),
        "config": {
            "captura_habilitada": fresca.captura.habilitada,
            "captura_intervalo_seg": fresca.captura.intervalo_seg,
            "monitor": fresca.captura.monitor,
            "desvio_sostenido_seg": fresca.alertas.desvio_sostenido_seg,
            "sesion_apps": list(fresca.sesion.apps),
            "sesion_aux": list(fresca.sesion.apps_auxiliares),
            "sesion_monitor_objetivo": fresca.sesion.monitor_objetivo,
            "sesion_fuera_app": fresca.sesion.segundos_fuera_app,
            "sesion_inactivo": fresca.sesion.segundos_inactivo,
            "sesion_ausencia_seg": fresca.sesion.ausencia_seg,
            "sesion_exigir_primer_plano": fresca.sesion.exigir_primer_plano,
            "modo": fresca.alertas.modo,
            "traer_al_frente_app": fresca.alertas.traer_al_frente_app,
            "traer_al_frente_tras": fresca.alertas.traer_al_frente_tras,
            "minutos_antes_de_traer": fresca.alertas.minutos_antes_de_traer,
            "nivel_1_apagado": fresca.alertas.nivel_1_apagado,
            "nivel_2_apagado": fresca.alertas.nivel_2_apagado,
            "nivel_3_apagado": fresca.alertas.nivel_3_apagado,
            "nivel_5_apagado": fresca.alertas.nivel_5_apagado,
            "refuerzo_positivo": fresca.alertas.refuerzo_positivo,
            "refuerzo_intervalo_min": fresca.alertas.refuerzo_intervalo_min,
            "mascota_visible": fresca.mascota.visible,
            "mascota_tema": fresca.mascota.tema,
            "avatar_proveedor": fresca.avatar.proveedor,
            "temas": list(TEMAS_MASCOTA),
            "camara_habilitada": fresca.camara.habilitada,
            "concentracion_habilitada": fresca.concentracion.habilitado,
            "concentracion_bloquear_hosts": fresca.concentracion.bloquear_hosts,
            "concentracion_silenciar_audio": fresca.concentracion.silenciar_audio,
            "concentracion_dominios": list(fresca.concentracion.dominios),
            "concentracion_apps_bloqueadas": list(fresca.concentracion.apps_bloqueadas),
            "presencia_habilitada": fresca.presencia.habilitada,
            "presencia_indice_camara": fresca.presencia.indice_camara,
            "presencia_intervalo_seg": fresca.presencia.intervalo_seg,
            "presencia_ausente_para_pausar_seg": fresca.presencia.ausente_para_pausar_seg,
            "presencia_telefono_en_mano_seg": fresca.presencia.telefono_en_mano_seg,
            "presupuesto_diario_usd": fresca.cerebro.presupuesto_diario_usd,
            "flujos_habilitado": fresca.flujos.habilitado,
            "flujos_aprendizaje": fresca.flujos.aprendizaje,
            "flujos_umbral_descubrimiento_min": fresca.flujos.umbral_descubrimiento_min,
            "flujos_grupos": list(fresca.flujos.grupo),
            "voz_segundos_escucha": getattr(getattr(fresca, "voz", None), "segundos_escucha", 8.0),
            "voz_segundos_n3": getattr(getattr(fresca, "voz", None), "segundos_n3", 7.0),
        },
        "prohibiciones": prohibiciones,
    }


def payload_reporte_semanal(cfg: Config, dias: int = 7) -> dict:
    try:
        db = EventDB(cfg.ruta_db)
        reporte = db.resumen_semanal(dias=dias)
        db.cerrar()
        return {"ok": True, "reporte": reporte}
    except Exception as exc:
        log.exception("Error al generar reporte semanal")
        return {"ok": False, "error": str(exc)}


# --------------------------------------------------------------------------- #
# Validación del POST /api/config (clamp + rechazo de claves raras)
# --------------------------------------------------------------------------- #

def _clamp(v, lo, hi, nombre: str):
    try:
        v = type(lo)(v)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre}: se esperaba un número")
    return max(lo, min(hi, v))


def _lista_unica(valores) -> list[str]:
    """Lista de apps normalizada: minúsculas, sin vacíos, sin repetidos, máx 8."""
    vistos: set[str] = set()
    salida: list[str] = []
    for valor in valores or []:
        texto = str(valor).strip().lower()[:64]
        if texto and texto not in vistos and len(salida) < 8:
            vistos.add(texto)
            salida.append(texto)
    return salida


def construir_overlay(payload: dict) -> dict:
    """Convierte el JSON del panel en el overlay para user.toml."""
    conocidas = {
        "captura", "alertas", "sesion", "mascota", "prohibiciones",
        "concentracion", "presencia", "flujos", "avatar",
    }
    desconocidas = set(payload) - conocidas
    if desconocidas:
        raise ValueError(f"claves desconocidas: {sorted(desconocidas)}")
    overlay: dict = {}

    if "captura" in payload:
        cap = payload["captura"] or {}
        seccion = {}
        if "habilitada" in cap:
            seccion["habilitada"] = bool(cap["habilitada"])
        if "intervalo_seg" in cap:
            seccion["intervalo_seg"] = _clamp(cap["intervalo_seg"], 5, 60, "intervalo")
        if "monitor" in cap:
            seccion["monitor"] = _clamp(cap["monitor"], 1, 16, "monitor")
        if seccion:
            overlay["captura"] = seccion

    if "alertas" in payload:
        al = payload["alertas"] or {}
        seccion = {}
        if "desvio_sostenido_seg" in al:
            seccion["desvio_sostenido_seg"] = _clamp(
                al["desvio_sostenido_seg"], 20, 300, "desvio_sostenido_seg"
            )
        if "modo" in al:
            modo = str(al["modo"])
            if modo not in MODOS:
                raise ValueError(f"modo inválido: {modo!r}")
            seccion["modo"] = modo
        if "traer_al_frente_app" in al:
            app = str(al["traer_al_frente_app"] or "").strip().lower()
            if len(app) > 64:
                raise ValueError("traer_al_frente_app demasiado largo")
            seccion["traer_al_frente_app"] = app
        if "traer_al_frente_tras" in al:
            seccion["traer_al_frente_tras"] = _clamp(
                al["traer_al_frente_tras"], 1, 5, "traer_al_frente_tras"
            )
        if "minutos_antes_de_traer" in al:
            seccion["minutos_antes_de_traer"] = _clamp(
                al["minutos_antes_de_traer"], 0, 30, "minutos_antes_de_traer"
            )
        if "nivel_1_apagado" in al:
            seccion["nivel_1_apagado"] = bool(al["nivel_1_apagado"])
        if "nivel_2_apagado" in al:
            seccion["nivel_2_apagado"] = bool(al["nivel_2_apagado"])
        if "nivel_3_apagado" in al:
            seccion["nivel_3_apagado"] = bool(al["nivel_3_apagado"])
        if "nivel_5_apagado" in al:
            seccion["nivel_5_apagado"] = bool(al["nivel_5_apagado"])
        if "refuerzo_positivo" in al:
            seccion["refuerzo_positivo"] = bool(al["refuerzo_positivo"])
        if "refuerzo_intervalo_min" in al:
            seccion["refuerzo_intervalo_min"] = _clamp(
                al["refuerzo_intervalo_min"], 1, 60, "refuerzo_intervalo_min"
            )
        if seccion:
            overlay["alertas"] = seccion

    if "sesion" in payload:
        se = payload["sesion"] or {}
        seccion = {}
        if "apps" in se:
            seccion["apps"] = _lista_unica(se.get("apps"))
        if "apps_auxiliares" in se:
            seccion["apps_auxiliares"] = _lista_unica(se.get("apps_auxiliares"))
        if "monitor_objetivo" in se:
            seccion["monitor_objetivo"] = _clamp(
                se["monitor_objetivo"], 0, 16, "monitor_objetivo"
            )
        if "segundos_fuera_app" in se:
            seccion["segundos_fuera_app"] = _clamp(
                se["segundos_fuera_app"], 10, 600, "segundos_fuera_app"
            )
        if "segundos_inactivo" in se:
            seccion["segundos_inactivo"] = _clamp(
                se["segundos_inactivo"], 10, 600, "segundos_inactivo"
            )
        if "ausencia_seg" in se:
            seccion["ausencia_seg"] = _clamp(
                se["ausencia_seg"], 0, 3600, "ausencia_seg"
            )
        if "exigir_primer_plano" in se:
            seccion["exigir_primer_plano"] = bool(se["exigir_primer_plano"])
        if seccion:
            overlay["sesion"] = seccion

    if "mascota" in payload:
        ma = payload["mascota"] or {}
        seccion = {}
        if "visible" in ma:
            seccion["visible"] = bool(ma["visible"])
        if "tema" in ma:
            tema = str(ma["tema"])
            if tema not in TEMAS_MASCOTA:
                raise ValueError(f"tema inválido: {tema!r}")
            seccion["tema"] = tema
        if seccion:
            overlay["mascota"] = seccion

    if "mascota" in payload:
        ma = payload["mascota"] or {}
        seccion = {}
        if "visible" in ma:
            seccion["visible"] = bool(ma["visible"])
        if "tema" in ma:
            tema = str(ma["tema"])
            if tema not in TEMAS_MASCOTA:
                raise ValueError(f"tema inválido: {tema!r}")
            seccion["tema"] = tema
        if seccion:
            overlay["mascota"] = seccion

    if "concentracion" in payload:
        cc = payload["concentracion"] or {}
        seccion = {}
        if "habilitado" in cc:
            seccion["habilitado"] = bool(cc["habilitado"])
        if "bloquear_hosts" in cc:
            seccion["bloquear_hosts"] = bool(cc["bloquear_hosts"])
        if "silenciar_audio" in cc:
            seccion["silenciar_audio"] = bool(cc["silenciar_audio"])
        if "dominios" in cc:
            dominios = [
                str(d).strip().lower()[:64]
                for d in (cc["dominios"] or [])
                if str(d).strip()
            ][:12]
            seccion["dominios"] = dominios
        if "apps_bloqueadas" in cc:
            apps = [
                str(a).strip().lower()[:64]
                for a in (cc["apps_bloqueadas"] or [])
                if str(a).strip()
            ][:12]
            seccion["apps_bloqueadas"] = apps
        if "duracion_min" in cc:
            seccion["duracion_min"] = _clamp(cc["duracion_min"], 0, 1440, "duracion_min")
        if seccion:
            overlay["concentracion"] = seccion

    if "presencia" in payload:
        pp = payload["presencia"] or {}
        seccion = {}
        if "habilitada" in pp:
            seccion["habilitada"] = bool(pp["habilitada"])
        if "indice_camara" in pp:
            seccion["indice_camara"] = _clamp(pp["indice_camara"], 0, 16, "indice_camara")
        if "intervalo_seg" in pp:
            seccion["intervalo_seg"] = _clamp(pp["intervalo_seg"], 5, 300, "intervalo_seg")
        if "ausente_para_pausar_seg" in pp:
            seccion["ausente_para_pausar_seg"] = _clamp(
                pp["ausente_para_pausar_seg"], 0, 3600, "ausente_para_pausar_seg"
            )
        if "telefono_en_mano_seg" in pp:
            seccion["telefono_en_mano_seg"] = _clamp(
                pp["telefono_en_mano_seg"], 0, 300, "telefono_en_mano_seg"
            )
        if seccion:
            overlay["presencia"] = seccion

    if "prohibiciones" in payload:
        lista = (payload["prohibiciones"] or {}).get("lista") or []
        if not isinstance(lista, list) or len(lista) > MAX_PROHIBICIONES:
            raise ValueError(f"prohibiciones: máximo {MAX_PROHIBICIONES} entradas")
        normalizada = []
        vistos = set()
        for entrada in lista:
            patron = str(entrada.get("patron", "") or "").strip().lower()
            if not patron or len(patron) > 64:
                raise ValueError("patrón de prohibición vacío o demasiado largo")
            if patron in vistos:
                continue
            vistos.add(patron)
            excepciones = []
            for exc in entrada.get("excepciones") or []:
                exc = str(exc).strip().lower()[:64]
                if exc:
                    excepciones.append(exc)
            if len(excepciones) > 8:
                raise ValueError(
                    f"prohibición {patron!r}: máximo 8 excepciones"
                )
            normalizada.append(
                {
                    "patron": patron,
                    "limite_min_dia": _clamp(
                        entrada.get("limite_min_dia", 60), 5, 480, "limite_min_dia"
                    ),
                    "bloqueo_activo": bool(entrada.get("bloqueo_activo", False)),
                    "excepciones": excepciones,
                }
            )
        overlay["prohibiciones"] = {"lista": normalizada}

    if "flujos" in payload:
        fl = payload["flujos"] or {}
        seccion = {}
        if "habilitado" in fl:
            seccion["habilitado"] = bool(fl["habilitado"])
        if "aprendizaje" in fl:
            seccion["aprendizaje"] = bool(fl["aprendizaje"])
        if "umbral_descubrimiento_min" in fl:
            seccion["umbral_descubrimiento_min"] = _clamp(
                fl["umbral_descubrimiento_min"], 1, 60, "umbral_descubrimiento_min"
            )
        if "grupo" in fl:
            grupos = []
            for g in (fl["grupo"] or []):
                if not isinstance(g, dict):
                    continue
                nombre = str(g.get("nombre", "") or "").strip().lower()[:64]
                if not nombre:
                    continue
                apps = _lista_unica(g.get("apps"))
                apps_rel = _lista_unica(g.get("apps_relacionadas"))
                tol = float(_clamp(g.get("tolerancia_min", 2.0), 0.5, 60.0, "tolerancia_min"))
                msg = str(g.get("mensaje_aviso", "") or "").strip()[:100]
                grupos.append({
                    "nombre": nombre,
                    "apps": apps,
                    "apps_relacionadas": apps_rel,
                    "tolerancia_min": tol,
                    "mensaje_aviso": msg,
                })
            seccion["grupo"] = grupos
        if seccion:
            overlay["flujos"] = seccion

    if "avatar" in payload:
        av = payload["avatar"] or {}
        seccion = {}
        if "proveedor" in av:
            prov = str(av["proveedor"]).strip().lower()
            if prov in ("auto", "embed", "openpets", "tk", "ninguno"):
                seccion["proveedor"] = prov
        if "mascota" in av:
            seccion["mascota"] = str(av["mascota"]).strip().lower()[:64]
        if "frases" in av:
            seccion["frases"] = bool(av["frases"])
        if seccion:
            overlay["avatar"] = seccion

    if not overlay:
        raise ValueError("nada que guardar")
    return overlay


# --------------------------------------------------------------------------- #
# Servidor
# --------------------------------------------------------------------------- #

class PanelServidor:
    """HTTP en 127.0.0.1 con la SPA estática + la API JSON."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._httpd: ThreadingHTTPServer | None = None
        self._hilo: threading.Thread | None = None

    # ------------------------------------------------------------------ #

    @property
    def puerto(self) -> int:
        return self._httpd.server_address[1] if self._httpd else self.cfg.panel.puerto

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.puerto}"

    def arrancar(self, abrir_navegador: bool = False) -> bool:
        panel = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            # ----- estáticos -----
            def _archivo(self, nombre: str, tipo: str) -> None:
                ruta = STATIC_DIR / nombre
                try:
                    cuerpo = ruta.read_bytes()
                except OSError:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(cuerpo)

            def do_GET(self) -> None:  # noqa: N802 (nombre de http.server)
                parsed = urllib.parse.urlparse(self.path)
                ruta_limpia = parsed.path
                if ruta_limpia in ("/", "/index.html"):
                    self._archivo(
                        "index.html", "text/html; charset=utf-8"
                    )
                elif ruta_limpia == "/estilos.css":
                    self._archivo("estilos.css", "text/css; charset=utf-8")
                elif ruta_limpia == "/aplicacion.js":
                    self._archivo(
                        "aplicacion.js", "application/javascript; charset=utf-8"
                    )
                elif ruta_limpia == "/pet-widget.html":
                    self._archivo("pet-widget.html", "text/html; charset=utf-8")
                elif ruta_limpia.startswith("/pets/"):
                    # Servir assets de mascotas (spritesheet.webp, pet.json)
                    partes = [p for p in ruta_limpia.split("/") if p]
                    if len(partes) >= 2:
                        sub = Path(*partes[1:])
                        pets_dir = (STATIC_DIR / "pets").resolve()
                        try:
                            ruta = (pets_dir / sub).resolve()
                        except Exception:
                            self.send_error(400, "Ruta inválida")
                            return
                        if not ruta.is_relative_to(pets_dir):
                            self.send_error(403, "Acceso denegado")
                            return
                        if not ruta.is_file() and partes[-1] == "spritesheet.webp":
                            pet_dir = (pets_dir / partes[1]).resolve()
                            if pet_dir.is_relative_to(pets_dir) and pet_dir.is_dir():
                                hallados = list(pet_dir.glob("**/spritesheet.webp"))
                                if hallados:
                                    ruta = hallados[0].resolve()
                        if ruta.is_file() and ruta.is_relative_to(pets_dir):
                            tipo = "image/webp" if ruta.suffix == ".webp" else "application/json"
                            try:
                                cuerpo = ruta.read_bytes()
                                self.send_response(200)
                                self.send_header("Content-Type", tipo)
                                self.send_header("Content-Length", str(len(cuerpo)))
                                self.send_header("Cache-Control", "public, max-age=3600")
                                self.end_headers()
                                self.wfile.write(cuerpo)
                                return
                            except OSError:
                                pass
                    self.send_error(404)
                elif ruta_limpia == "/api/pet/state":
                    self._responder(200, pet_estado_actual())
                elif ruta_limpia == "/api/pet/list":
                    self._responder(200, {"ok": True, "pets": pet_listar_disponibles()})

                elif ruta_limpia == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                elif ruta_limpia.startswith("/api/reporte/semanal"):
                    self._responder(200, payload_reporte_semanal(panel.cfg))
                elif ruta_limpia == "/api/estado":
                    cuerpo = json.dumps(
                        payload_estado(panel.cfg), ensure_ascii=False
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "application/json; charset=utf-8"
                    )
                    self.send_header("Content-Length", str(len(cuerpo)))
                    self.end_headers()
                    self.wfile.write(cuerpo)
                else:
                    self.send_error(404)

            # ----- API -----
            def do_POST(self) -> None:  # noqa: N802
                # Validar Origin para mitigar CSRF desde páginas externas
                origin = self.headers.get("Origin")
                if origin:
                    origenes_validos = (
                        f"http://127.0.0.1:{panel.puerto}",
                        f"http://localhost:{panel.puerto}",
                    )
                    if origin not in origenes_validos:
                        self._responder(403, {"ok": False, "error": "Origin no permitido"})
                        return
                if self.path == "/api/config":
                    self._api_config()
                elif self.path == "/api/control":
                    self._api_control()
                elif self.path == "/api/detectar":
                    self._api_detectar()
                elif self.path == "/api/pet/say":
                    self._api_pet_say()
                elif self.path == "/api/pet/set-pet":
                    self._api_pet_set_pet()
                elif self.path == "/api/pet/responder":
                    self._api_pet_responder()
                else:
                    self.send_error(404)

            def _api_pet_say(self) -> None:
                try:
                    datos = self._leer_json()
                except Exception as exc:
                    self._responder(400, {"ok": False, "error": str(exc)})
                    return
                pet_decir(
                    texto=datos.get("mensaje", ""),
                    reaccion=datos.get("reaction"),
                    opciones=datos.get("opciones"),
                    duracion_ms=datos.get("duracion", 4000),
                )
                self._responder(200, {"ok": True})

            def _api_pet_set_pet(self) -> None:
                try:
                    datos = self._leer_json()
                except Exception as exc:
                    self._responder(400, {"ok": False, "error": str(exc)})
                    return
                mascota = str(datos.get("mascota", "null-wisp")).strip()
                pet_fijar_mascota(mascota)
                self._responder(200, {"ok": True, "mascota": mascota})

            def _api_pet_responder(self) -> None:
                try:
                    datos = self._leer_json()
                except Exception as exc:
                    self._responder(400, {"ok": False, "error": str(exc)})
                    return
                respuesta = str(datos.get("respuesta", "")).strip()
                if respuesta:
                    pet_registrar_respuesta(respuesta)
                self._responder(200, {"ok": True, "registrado": respuesta})

            def _leer_json(self, tope: int = 64 * 1024) -> dict:
                largo = int(self.headers.get("Content-Length") or 0)
                if largo <= 0 or largo > tope:
                    raise ValueError("cuerpo vacío o demasiado grande")
                datos = json.loads(self.rfile.read(largo).decode("utf-8"))
                if not isinstance(datos, dict):
                    raise ValueError("se esperaba un objeto JSON")
                return datos

            def _responder(self, codigo: int, datos: dict) -> None:
                cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
                self.send_response(codigo)
                self.send_header(
                    "Content-Type", "application/json; charset=utf-8"
                )
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def _api_config(self) -> None:
                try:
                    overlay = construir_overlay(self._leer_json())
                    ruta_user = (panel.cfg._config_dir or Path(".")) / "user.toml"
                    escribir_user_toml(ruta_user, overlay)
                    panel.cfg._huella_user = None  # fuerza recarga en el agente
                except Exception as exc:
                    self._responder(400, {"ok": False, "error": str(exc)[:200]})
                    return
                self._responder(
                    200,
                    {
                        "ok": True,
                        "nota": (
                            "Guardado en config/user.toml. Si el agente está "
                            "corriendo, se aplica en el próximo ciclo (<= 15 s)."
                        ),
                    },
                )

            def _api_control(self) -> None:
                try:
                    datos = self._leer_json()
                except Exception as exc:
                    self._responder(400, {"ok": False, "error": str(exc)[:200]})
                    return
                cmd = str(datos.get("cmd", ""))
                permitidos = {
                    "pause", "pause_manual", "resume", "resume_or_extend",
                    "stop", "task", "test_alert",
                    "session_start", "session_stop", "privado",
                }
                if cmd not in permitidos:
                    self._responder(400, {"ok": False, "error": f"cmd desconocido: {cmd!r}"})
                    return
                salida = {"cmd": cmd}
                if cmd in ("pause", "pause_manual"):
                    salida["minutos"] = _clamp(
                        datos.get("minutos", 15), 1, 480, "minutos"
                    )
                    salida["espera_confirmacion"] = bool(datos.get("espera_confirmacion", False))
                elif cmd == "resume_or_extend":
                    salida["minutos"] = _clamp(
                        datos.get("minutos", 15), 1, 480, "minutos"
                    )
                elif cmd == "task":
                    salida["texto"] = str(datos.get("texto", ""))[:200]
                elif cmd == "session_start":
                    apps = [
                        str(a).strip().lower()[:64]
                        for a in (datos.get("apps") or [])
                        if str(a).strip()
                    ][:8]
                    aux = [
                        str(a).strip().lower()[:64]
                        for a in (datos.get("aux") or [])
                        if str(a).strip()
                    ][:8]
                    salida.update(
                        {
                            "texto": str(datos.get("texto", ""))[:200] or "sesión",
                            "apps": apps,
                            "apps_aux": aux,
                            "minutos": _clamp(datos.get("minutos", 0), 0, 480, "minutos"),
                        }
                    )
                elif cmd == "privado":
                    salida["valor"] = bool(datos.get("valor", False))
                ruta = panel.cfg.ruta_control
                try:
                    ruta.parent.mkdir(parents=True, exist_ok=True)
                    tmp = ruta.with_suffix(".tmp")
                    tmp.write_text(
                        json.dumps(salida, ensure_ascii=False), encoding="utf-8"
                    )
                    tmp.replace(ruta)
                except OSError as exc:
                    self._responder(500, {"ok": False, "error": str(exc)[:200]})
                    return
                self._responder(200, {"ok": True, "cmd": cmd})

            def _api_detectar(self) -> None:
                """v0.5.0: muestrea el primer plano y propone apps de la sesión."""
                try:
                    datos = self._leer_json()
                except Exception:
                    datos = {}
                segundos = _clamp(datos.get("segundos", 10), 3, 30, "segundos")
                from yourfocusguard.capture import window_info

                fresca = _config_fresca(panel.cfg)
                muestras = window_info.apps_mas_usadas(
                    segundos, 1.0, fresca.heuristica.apps_neutras, gracia=2.0
                )
                total = sum(n for _, n in muestras) or 1
                apps = [app for app, n in muestras if n / total >= 0.10][:5]
                self._responder(
                    200,
                    {
                        "ok": True,
                        "apps": apps,
                        "segundos": segundos,
                        "muestra": [
                            {"app": app, "pct": round(100 * n / total)}
                            for app, n in muestras[:8]
                        ],
                    },
                )

            def log_message(self, formato: str, *args) -> None:  # silencio amable
                primer = str(args[0]) if args else ""
                if "/api/" in primer:
                    log.debug("panel %s", primer)

        try:
            self._httpd = ThreadingHTTPServer(
                ("127.0.0.1", self.cfg.panel.puerto), Handler
            )
            self._httpd.daemon_threads = True
        except OSError as exc:
            log.warning("no se pudo abrir el panel (puerto %s): %s",
                        self.cfg.panel.puerto, exc)
            return False
        self._hilo = threading.Thread(
            target=self._httpd.serve_forever,
            name="yfg-panel",
            daemon=True,
        )
        self._hilo.start()
        log.info("Panel del Guardián en %s", self.url)
        if abrir_navegador:
            threading.Timer(1.0, webbrowser.open, (self.url,)).start()
        return True

    def parar(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:  # pragma: no cover
                pass
            self._httpd = None
        if self._hilo is not None:
            self._hilo.join(timeout=3.0)
            self._hilo = None

    def servir_para_siempre(self) -> None:
        """Bloquea (para `run.py panel`); sale con Ctrl+C."""
        try:
            while self._hilo is not None:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            self.parar()
