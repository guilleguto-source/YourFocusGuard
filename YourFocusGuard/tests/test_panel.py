"""Pruebas del Panel del Guardián (v0.3.0): API, validación y user.toml.

El panel se prueba con un config/ AISLADO en tmp_path: nunca escribe en el
config/ real del proyecto (una fuga ahí contamina al resto de la suite)."""
from __future__ import annotations

import json
import shutil
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from yourfocusguard.config import escribir_user_toml, load_config
from yourfocusguard.panel import (
    PanelServidor,
    construir_overlay,
    payload_estado,
)


def _puerto_libre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


@pytest.fixture()
def cfg(tmp_path):
    """Config aislada (default+pc copiados a tmp) para no tocar config/ real."""
    origen = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copy(origen / "default.toml", config_dir / "default.toml")
    shutil.copy(origen / "pc.toml", config_dir / "pc.toml")
    c = load_config(
        perfil="pc", config_dir=config_dir, datos_carpeta=str(tmp_path / "data")
    )
    c.mascota.visible = False
    return c


@pytest.fixture()
def panel(cfg):
    cfg.panel.puerto = _puerto_libre()
    cfg.panel.abrir_navegador = False
    servidor = PanelServidor(cfg)
    assert servidor.arrancar()
    yield servidor
    servidor.parar()
    # cortesía: que no quede control.json suelto entre tests
    try:
        cfg.ruta_control.unlink(missing_ok=True)
    except OSError:
        pass


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read()


def _post(url, datos):
    req = urllib.request.Request(
        url,
        data=json.dumps(datos).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# --------------------------------------------------------------------------- #
# Páginas estáticas y API de lectura
# --------------------------------------------------------------------------- #

def test_index_y_estilos_sirven(panel):
    estado, html = _get(f"{panel.url}/")
    assert estado == 200
    assert "Panel del Guardián".encode() in html
    assert b"prohibiciones" in html
    estado, css = _get(f"{panel.url}/estilos.css")
    assert estado == 200
    assert b"--fondo" in css and b"#e8e4db" in css  # greige, nunca blanco


def test_api_estado_trae_config_y_prohibiciones(panel, cfg):
    import sys

    estado, crudo = _get(f"{panel.url}/api/estado")
    assert estado == 200
    cuerpo = json.loads(crudo)
    assert cuerpo["config"]["modo"] in ("visual", "visual_sonoro", "completo")
    assert cuerpo["config"]["temas"] == ["clasico", "oscuro", "calido"]
    assert cuerpo["corriendo"] is False  # sin agente, sin state.json
    if sys.platform == "win32":
        # En Windows real el panel lista los monitores físicos; la lista puede
        # estar vacía en una sesión sin escritorio, pero debe ser una lista.
        assert isinstance(cuerpo["monitores"], list)
    else:
        assert cuerpo["monitores"] == []  # fuera de Windows


def test_payload_prohibiciones_con_db(cfg):
    """El panel muestra el progreso de hoy fusionando config + SQLite."""
    from yourfocusguard.config import ProhibicionCfg
    from yourfocusguard.storage.db import EventDB

    # persistir la prohibición como haría el panel (payload lee de disco)
    escribir_user_toml(
        cfg._config_dir / "user.toml",
        {
            "prohibiciones": {
                "lista": [
                    {"patron": "youtube", "limite_min_dia": 60, "bloqueo_activo": True}
                ]
            }
        },
    )
    db = EventDB(cfg.ruta_db)
    db.presupuesto_sumar("youtube", 60 * 30)  # 30 min de 60
    db.cerrar()
    datos = payload_estado(cfg)
    assert datos["prohibiciones"][0]["usado_min"] == 30.0
    assert datos["prohibiciones"][0]["excedido"] is False


# --------------------------------------------------------------------------- #
# POST /api/config: validación, clamps y persistencia
# --------------------------------------------------------------------------- #

def test_guardar_config_escribe_user_toml(panel, cfg):
    estado, cuerpo = _post(
        f"{panel.url}/api/config",
        {
            "captura": {"intervalo_seg": 20, "monitor": 2},
            "alertas": {
                "desvio_sostenido_seg": 90,
                "modo": "visual_sonoro",
                "traer_al_frente_app": "Lightroom",
                "traer_al_frente_tras": 3,
            },
            "sesion": {"segundos_fuera_app": 90, "segundos_inactivo": 120},
            "mascota": {"visible": True, "tema": "calido"},
            "prohibiciones": {
                "lista": [
                    {"patron": "YouTube", "limite_min_dia": 60, "bloqueo_activo": True}
                ]
            },
        },
    )
    assert estado == 200 and cuerpo["ok"] is True

    # el archivo existe y lo carga otra capa de config
    ruta_user = cfg._config_dir / "user.toml"
    assert ruta_user.exists()
    cfg2 = load_config(
        perfil="pc", config_dir=cfg._config_dir, datos_carpeta=str(cfg.datos.carpeta)
    )
    assert cfg2.captura.intervalo_seg == 20
    assert cfg2.captura.monitor == 2
    assert cfg2.alertas.desvio_sostenido_seg == 90
    assert cfg2.alertas.modo == "visual_sonoro"
    assert cfg2.alertas.traer_al_frente_app == "lightroom"  # normalizado a minúsculas
    assert cfg2.alertas.traer_al_frente_tras == 3
    assert cfg2.sesion.segundos_fuera_app == 90
    assert cfg2.mascota.tema == "calido"
    assert cfg2.prohibiciones.lista[0].patron == "youtube"
    assert cfg2.prohibiciones.lista[0].bloqueo_activo is True


def test_clamps_y_rechazos(panel):
    # desvío fuera de rango -> se ajusta a 300, no error
    estado, cuerpo = _post(
        f"{panel.url}/api/config",
        {"alertas": {"desvio_sostenido_seg": 999}},
    )
    assert estado == 200
    # modo inválido -> 400
    estado, cuerpo = _post(
        f"{panel.url}/api/config", {"alertas": {"modo": "gritos"}}
    )
    assert estado == 400 and cuerpo["ok"] is False
    # tema inválido -> 400
    estado, cuerpo = _post(
        f"{panel.url}/api/config", {"mascota": {"tema": "arcoiris"}}
    )
    assert estado == 400
    # claves desconocidas -> 400
    estado, cuerpo = _post(f"{panel.url}/api/config", {"inventado": 1})
    assert estado == 400
    # lista demasiado larga -> 400
    estado, cuerpo = _post(
        f"{panel.url}/api/config",
        {
            "prohibiciones": {
                "lista": [
                    {"patron": f"p{i}", "limite_min_dia": 30} for i in range(13)
                ]
            }
        },
    )
    assert estado == 400
    # patrón vacío -> 400
    estado, cuerpo = _post(
        f"{panel.url}/api/config",
        {"prohibiciones": {"lista": [{"patron": "", "limite_min_dia": 30}]}},
    )
    assert estado == 400


def test_construir_overlay_deduplica_patrones():
    overlay = construir_overlay(
        {
            "prohibiciones": {
                "lista": [
                    {"patron": "YouTube", "limite_min_dia": 60, "bloqueo_activo": True},
                    {"patron": "youtube", "limite_min_dia": 30},
                ]
            }
        }
    )
    lista = overlay["prohibiciones"]["lista"]
    assert len(lista) == 1
    assert lista[0]["patron"] == "youtube"
    assert lista[0]["limite_min_dia"] == 60


# --------------------------------------------------------------------------- #
# POST /api/control: mismos comandos que la consola
# --------------------------------------------------------------------------- #

def test_control_pause_y_test_alert(panel, cfg):
    estado, cuerpo = _post(
        f"{panel.url}/api/control", {"cmd": "pause", "minutos": 25}
    )
    assert estado == 200 and cuerpo["ok"] is True
    data = json.loads(cfg.ruta_control.read_text(encoding="utf-8"))
    assert data["cmd"] == "pause" and data["minutos"] == 25

    estado, cuerpo = _post(f"{panel.url}/api/control", {"cmd": "test_alert"})
    assert estado == 200
    data = json.loads(cfg.ruta_control.read_text(encoding="utf-8"))
    assert data["cmd"] == "test_alert"

    estado, cuerpo = _post(f"{panel.url}/api/control", {"cmd": "nonsense"})
    assert estado == 400


def test_control_session_start_normaliza(panel, cfg):
    estado, _ = _post(
        f"{panel.url}/api/control",
        {
            "cmd": "session_start",
            "texto": "editar fotos de la boda",
            "apps": ["Lightroom", " photoshop "],
            "aux": ["Bridge"],
            "minutos": 90,
        },
    )
    assert estado == 200
    data = json.loads(cfg.ruta_control.read_text(encoding="utf-8"))
    assert data["apps"] == ["lightroom", "photoshop"]
    assert data["apps_aux"] == ["bridge"]
    assert data["minutos"] == 90


def test_construir_overlay_acepta_flujos():
    overlay = construir_overlay(
        {
            "flujos": {
                "habilitado": True,
                "aprendizaje": True,
                "umbral_descubrimiento_min": 3,
                "grupo": [
                    {
                        "nombre": "edicion_foto",
                        "apps": ["Lightroom", "Photoshop"],
                        "apps_relacionadas": ["Gutoflow", "Bridge"],
                        "tolerancia_min": 2.5,
                        "mensaje_aviso": "¿Volvemos?",
                    }
                ],
            }
        }
    )
    fl = overlay["flujos"]
    assert fl["habilitado"] is True
    assert fl["umbral_descubrimiento_min"] == 3
    assert len(fl["grupo"]) == 1
    assert fl["grupo"][0]["apps"] == ["lightroom", "photoshop"]
    assert fl["grupo"][0]["apps_relacionadas"] == ["gutoflow", "bridge"]


def test_panel_bloquea_path_traversal(panel):
    req = urllib.request.Request(f"{panel.url}/pets/../../../run.py")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=3.0)
    assert exc_info.value.code == 403


def test_panel_bloquea_csrf_origin_no_permitido(panel):
    req = urllib.request.Request(
        f"{panel.url}/api/control",
        data=b'{"cmd": "session_stop"}',
        headers={"Content-Type": "application/json", "Origin": "http://sitio-malicioso.com"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=3.0)
    assert exc_info.value.code == 403


def test_panel_api_reporte_semanal(panel):
    estado, cuerpo_raw = _get(f"{panel.url}/api/reporte/semanal")
    assert estado == 200
    cuerpo = json.loads(cuerpo_raw.decode("utf-8"))
    assert cuerpo.get("ok") is True
    assert "reporte" in cuerpo
    rep = cuerpo["reporte"]
    assert "minutos_foco_total" in rep
    assert "total_desvios" in rep
    assert "top_apps_distraccion" in rep


