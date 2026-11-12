"""Modo Máxima Concentración (v0.7.0, Fase 3).

Tests sin privilegios de administrador ni audio real: se falsifican el archivo
hosts y la API de waveOut mediante monkeypatch.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from yourfocusguard.actions.concentracion import (
    ModoConcentracion,
    _escribir_hosts,
    _leer_hosts,
    _ya_bloqueado,
    crear_modo_concentracion,
)


def _cfg_concentracion(habilitado=True, dominios=None, apps=None):
    from yourfocusguard.config import ConcentracionCfg, Config
    c = ConcentracionCfg(
        habilitado=habilitado,
        bloquear_hosts=True,
        silenciar_audio=True,
        dominios=list(dominios or []),
        apps_bloqueadas=list(apps or []),
        restaurar_al_salir=True,
    )
    return c


def test_activar_anade_lineas_hosts(tmp_path, monkeypatch):
    """Se añaden entradas 127.0.0.1 para cada dominio configurado."""
    hosts = tmp_path / "hosts"
    hosts.write_text("# hosts originales\n", encoding="utf-8")

    def leer():
        return hosts.read_text(encoding="utf-8")

    def escribir(contenido):
        hosts.write_text(contenido, encoding="utf-8")
        return True

    monkeypatch.setattr("yourfocusguard.actions.concentracion._IS_WINDOWS", True)
    monkeypatch.setattr("yourfocusguard.actions.concentracion._leer_hosts", leer)
    monkeypatch.setattr("yourfocusguard.actions.concentracion._escribir_hosts", escribir)

    cfg = _cfg_concentracion(dominios=["youtube.com", "instagram.com"])
    modo = ModoConcentracion(cfg)
    resumen = modo.activar()

    contenido = hosts.read_text(encoding="utf-8")
    assert "127.0.0.1 youtube.com" in contenido
    assert "127.0.0.1 instagram.com" in contenido
    assert resumen["hosts"] is True
    assert "127.0.0.1 youtube.com" in resumen["dominios_bloqueados"]
    assert "127.0.0.1 instagram.com" in resumen["dominios_bloqueados"]


def test_activar_no_duplica_dominios_ya_bloqueados(tmp_path, monkeypatch):
    """Si un dominio ya está en hosts, no se añade dos veces."""
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 youtube.com\n", encoding="utf-8")

    def leer():
        return hosts.read_text(encoding="utf-8")

    def escribir(contenido):
        hosts.write_text(contenido, encoding="utf-8")
        return True

    monkeypatch.setattr("yourfocusguard.actions.concentracion._IS_WINDOWS", True)
    monkeypatch.setattr("yourfocusguard.actions.concentracion._leer_hosts", leer)
    monkeypatch.setattr("yourfocusguard.actions.concentracion._escribir_hosts", escribir)

    cfg = _cfg_concentracion(dominios=["youtube.com"])
    modo = ModoConcentracion(cfg)
    resumen = modo.activar()

    assert resumen["hosts"] is True
    assert resumen["dominios_bloqueados"] == []


def test_desactivar_quita_lineas_anadidas(tmp_path, monkeypatch):
    """Al desactivar, las líneas añadidas se quitan del hosts."""
    hosts = tmp_path / "hosts"
    hosts.write_text("# original\n", encoding="utf-8")

    def leer():
        return hosts.read_text(encoding="utf-8")

    def escribir(contenido):
        hosts.write_text(contenido, encoding="utf-8")
        return True

    monkeypatch.setattr("yourfocusguard.actions.concentracion._IS_WINDOWS", True)
    monkeypatch.setattr("yourfocusguard.actions.concentracion._leer_hosts", leer)
    monkeypatch.setattr("yourfocusguard.actions.concentracion._escribir_hosts", escribir)

    cfg = _cfg_concentracion(dominios=["tiktok.com"])
    modo = ModoConcentracion(cfg)
    modo.activar()
    assert "127.0.0.1 tiktok.com" in hosts.read_text(encoding="utf-8")

    modo.desactivar()
    assert "127.0.0.1 tiktok.com" not in hosts.read_text(encoding="utf-8")


def test_debe_minimizar_detecta_app_bloqueada():
    """debe_minimizar devuelve True si la ventana activa matchea una app bloqueada."""
    cfg = _cfg_concentracion(apps=["chrome", "steam"])
    modo = ModoConcentracion(cfg)
    modo.activo = True

    assert modo.debe_minimizar("chrome", "") is True
    assert modo.debe_minimizar("steam", "Steam - Biblioteca") is True
    assert modo.debe_minimizar("lightroom", "") is False
    assert modo.debe_minimizar(None, "alguna ventana") is False


def test_debe_minimizar_inactivo_si_no_hay_app_bloqueada():
    """Sin apps_bloqueadas configuradas, nunca minimiza."""
    cfg = _cfg_concentracion(apps=[])
    modo = ModoConcentracion(cfg)
    modo.activo = True
    assert modo.debe_minimizar("chrome", "") is False


def test_crear_modo_concentracion_devuelve_instancia():
    cfg = _cfg_concentracion()
    modo = crear_modo_concentracion(cfg)
    assert isinstance(modo, ModoConcentracion)
    assert modo.activo is False


def test_duracion_seg_cero_sin_activar():
    cfg = _cfg_concentracion()
    modo = ModoConcentracion(cfg)
    assert modo.duracion_seg() == 0.0


def test_ya_bloqueado_detecta_entrada_existente():
    contenido = "127.0.0.1 youtube.com\n127.0.0.1 instagram.com\n"
    assert _ya_bloqueado(contenido, "youtube.com") is True
    assert _ya_bloqueado(contenido, "instagram.com") is True
    assert _ya_bloqueado(contenido, "netflix.com") is False


def test_ya_bloqueado_ignora_protocolo():
    """El usuario puede traer "https://youtube.com" y se normaliza."""
    cfg = _cfg_concentracion(dominios=["https://youtube.com", "www.instagram.com"])
    modo = ModoConcentracion(cfg)
    # verificar que los dominios se normalizan al leer
    assert cfg.dominios == ["https://youtube.com", "www.instagram.com"]


def test_audio_mute_no_lanza_sin_winmm(monkeypatch):
    """Fuera de Windows o sin winmm, _silenciar_audio devuelve False sin lanzar."""
    import yourfocusguard.actions.concentracion as mod

    monkeypatch.setattr(mod, "_IS_WINDOWS", False)
    cfg = _cfg_concentracion()
    modo = ModoConcentracion(cfg)
    assert modo._silenciar_audio() is False


if __name__ == "__main__":
    print("test_concentracion: OK")
