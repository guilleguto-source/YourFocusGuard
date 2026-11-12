"""Pruebas de la carga de configuración TOML por capas."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from yourfocusguard.config import load_config


def test_perfil_pc_por_defecto(cfg):
    assert cfg.agente.maquina == "pc_diseno"
    assert cfg.cerebro.proveedor_nube == "gemini"
    assert cfg.captura.intervalo_seg == 15
    assert cfg.captura.fifo_frames == 5
    # umbrales de la tabla 5
    assert cfg.alertas.desvio_sostenido_seg == 30
    assert cfg.alertas.aviso_seg == 30
    assert cfg.alertas.toast_seg == 60
    assert cfg.alertas.voz_seg == 90
    assert cfg.alertas.enfriamiento_seg == 300
    assert cfg.alertas.tope_por_hora == 4
    assert cfg.cerebro.confianza_minima == 0.6
    assert cfg.heuristica.idle_ausencia_seg == 120


def test_perfil_laptop(cfg_laptop):
    assert cfg_laptop.agente.maquina == "laptop"
    assert cfg_laptop.cerebro.proveedor_nube == "ninguno"
    assert cfg_laptop.captura.intervalo_seg == 20
    # lo no sobreescrito hereda de default
    assert cfg_laptop.alertas.voz_seg == 90


def test_rutas_derivadas(cfg, tmp_path):
    base = tmp_path / "data"
    assert cfg.ruta_db == base / "yourfocusguard.db"
    assert cfg.ruta_estado == base / "state.json"
    assert cfg.ruta_control == base / "control.json"
    assert cfg.ruta_log == base / "logs" / "agente.log"


def test_capa_user_toml_pisa(tmp_path):
    """user.toml gana sobre default y perfil."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    origen = Path(__file__).resolve().parents[1] / "config"
    (config_dir / "default.toml").write_bytes((origen / "default.toml").read_bytes())
    (config_dir / "pc.toml").write_bytes((origen / "pc.toml").read_bytes())
    (config_dir / "user.toml").write_text(
        '[alertas]\ndesvio_sostenido_seg = 25\n', encoding="utf-8"
    )
    cfg = load_config(perfil="pc", config_dir=config_dir, datos_carpeta=str(tmp_path / "d"))
    assert cfg.alertas.desvio_sostenido_seg == 25
    assert cfg.alertas.toast_seg == 60  # intacto


def test_seccion_desconocida_rechazada(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    origen = Path(__file__).resolve().parents[1] / "config"
    (config_dir / "default.toml").write_bytes((origen / "default.toml").read_bytes())
    (config_dir / "pc.toml").write_text("[inventada]\nclave = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="secciones desconocidas"):
        load_config(perfil="pc", config_dir=config_dir)


def test_intervalo_menor_que_5_rechazado(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    origen = Path(__file__).resolve().parents[1] / "config"
    (config_dir / "default.toml").write_bytes((origen / "default.toml").read_bytes())
    (config_dir / "pc.toml").write_text("[captura]\nintervalo_seg = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="intervalo_seg"):
        load_config(perfil="pc", config_dir=config_dir)


def test_clave_desconocida_avisa(cfg, tmp_path, caplog):
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)  # el fixture cfg ya crea tmp/config
    origen = Path(__file__).resolve().parents[1] / "config"
    (config_dir / "default.toml").write_bytes((origen / "default.toml").read_bytes())
    (config_dir / "pc.toml").write_text("[alertas]\nintervalo_raro = 9\n", encoding="utf-8")
    import logging

    with caplog.at_level(logging.WARNING):
        c = load_config(perfil="pc", config_dir=config_dir)
    assert c.alertas.toast_seg == 60  # el resto intacto
    assert any("clave desconocida" in m for m in caplog.messages)


def test_perfil_invalido():
    with pytest.raises(ValueError, match="perfil"):
        load_config(perfil="servidor")


def test_default_toml_parsea_y_cubre_todo():
    """default.toml es TOML válido y define las listas del Nivel B."""
    ruta = Path(__file__).resolve().parents[1] / "config" / "default.toml"
    data = tomllib.loads(ruta.read_text(encoding="utf-8"))
    assert set(data) == {
        "agente", "captura", "cerebro", "heuristica", "alertas",
        "pomodoro", "sesion", "camara", "privacidad", "datos", "registro",
        # v0.3.0
        "prohibiciones", "mascota", "panel",
        # v0.6.0
        "avatar",
        # v0.7.0
        "concentracion",
        # v0.8.0
        "flujos",
        # v0.8.3
        "voz",
        "notas",
        "rutinas",
        "vikunja",
        "musica",
    }

    assert data["heuristica"]["apps_enfoque"]
    assert data["heuristica"]["titulos_distraccion"]
    assert data["privacidad"]["titulos_excluidos"]
    assert data["sesion"]["segundos_fuera_app"] > 0
    assert data["sesion"]["segundos_inactivo"] > 0
    # la webcam es opt-in: desactivada de fábrica (privacidad por defecto)
    assert data["camara"]["habilitada"] is False
    assert data["sesion"]["verificar_con_camara_seg"] > 0
    # v0.3.0: panel, mascota y prohibiciones san de fábrica
    assert data["panel"]["puerto"] == 8756
    assert data["mascota"]["visible"] is True
    assert data["prohibiciones"]["lista"] == []
    assert data["alertas"]["modo"] == "completo"
    assert data["voz"]["segundos_escucha"] == 8.0
    assert data["voz"]["segundos_n3"] == 7.0
    assert data["vikunja"]["habilitado"] is False
    assert data["musica"]["habilitado"] is True
    assert data["musica"]["volumen"] == 0.5


def test_voz_configuracion_y_poda():
    """Valida carga de VozCfg y función de poda preventiva de caché."""
    from yourfocusguard.actions.tts import podar_cache_audio
    assert podar_cache_audio(max_archivos=1000, max_mb=500.0) >= 0

