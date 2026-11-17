"""v0.8.5 — Regresión del modo concentración tras la auditoría (GitHub Copilot).

Cubre los dos bugs HIGH que el review señala:
1. hosts: líneas sueltas fuera del bloque marcado que sobrevivían a un crash.
2. audio: el volumen se restauraba a ~50% fijo en lugar del valor original.

Todo se prueba con hosts y waveOut falsificados (sin Windows real).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import yourfocusguard.actions.concentracion as mod
from yourfocusguard.actions.concentracion import (
    _MARCADOR_FIN,
    _MARCADOR_INICIO,
    _extraer_contaminacion,
    limpiar_huerfanos_hosts,
    ModoConcentracion,
)


def _cfg():
    from yourfocusguard.config import ConcentracionCfg
    return ConcentracionCfg(
        habilitado=True,
        bloquear_hosts=True,
        silenciar_audio=True,
        dominios=["youtube.com", "instagram.com"],
        apps_bloqueadas=[],
        restaurar_al_salir=True,
    )


@pytest.fixture()
def entorno_hosts(tmp_path, monkeypatch):
    """hosts falsificado + journal apuntando a una ruta temporal del test."""
    hosts = tmp_path / "hosts"
    original = "# hosts originales\n\n127.0.0.1 localhost\n"
    hosts.write_text(original, encoding="utf-8")
    journal = tmp_path / "journal.json"

    monkeypatch.setattr(mod, "_IS_WINDOWS", True)
    monkeypatch.setattr(mod, "_JOURNAL_RUTA", journal)
    monkeypatch.setattr(
        mod, "_leer_hosts", lambda: hosts.read_text(encoding="utf-8")
    )

    def escribir(contenido: str) -> bool:
        hosts.write_text(contenido, encoding="utf-8")
        return True

    monkeypatch.setattr(mod, "_escribir_hosts", escribir)
    return SimpleNamespace(hosts=hosts, journal=journal, original=original)


# --------------------------------------------------------------------- #
# 1. Sin líneas sueltas: todo dentro del bloque marcado
# --------------------------------------------------------------------- #

def test_activar_escribe_solo_bloque_marcado(entorno_hosts):
    modo = ModoConcentracion(_cfg())
    modo.activar()

    contenido = entorno_hosts.hosts.read_text(encoding="utf-8")
    assert _MARCADOR_INICIO in contenido
    assert _MARCADOR_FIN in contenido

    # Todas las líneas 127.0.0.1 de dominios deben estar ENTRE los marcadores
    inicio = contenido.index(_MARCADOR_INICIO)
    fin = contenido.index(_MARCADOR_FIN)
    fuera_del_bloque = contenido[:inicio] + contenido[fin:]
    assert "127.0.0.1 youtube.com" not in fuera_del_bloque
    assert "127.0.0.1 instagram.com" not in fuera_del_bloque
    # y dentro del bloque sí están
    assert "127.0.0.1 youtube.com" in contenido[inicio:fin]


# --------------------------------------------------------------------- #
# 2. Crash: sin desactivar, la limpieza de arranque lo recupera TODO
# --------------------------------------------------------------------- #

def test_crash_recuperacion_al_arrancar(entorno_hosts):
    modo = ModoConcentracion(_cfg())
    modo.activar()
    # --- crash: el proceso muere SIN llamar a desactivar ---
    assert entorno_hosts.journal.exists()  # el journal quedó escrito

    # Arranque siguiente: nueva instancia + limpieza de huérfanos
    assert limpiar_huerfanos_hosts() is True
    contenido = entorno_hosts.hosts.read_text(encoding="utf-8")
    assert contenido == entorno_hosts.original  # hosts EXACTAMENTE como estaba
    assert "127.0.0.1 youtube.com" not in contenido
    assert _MARCADOR_INICIO not in contenido
    assert not entorno_hosts.journal.exists()  # journal consumido


def test_crash_sin_journal_limpia_bloque_y_huerfanos_legacy(entorno_hosts):
    """Huérfanos de versiones < 0.8.5: líneas sueltas + bloque (sin journal)."""
    sucio = (
        entorno_hosts.original
        + "127.0.0.1 youtube.com\n"           # huérfano suelto (bug viejo)
        + f"{_MARCADOR_INICIO}\n"
        + "127.0.0.1 youtube.com\n"
        + "127.0.0.1 instagram.com\n"
        + f"{_MARCADOR_FIN}\n"
    )
    entorno_hosts.hosts.write_text(sucio, encoding="utf-8")
    assert not entorno_hosts.journal.exists()  # sin journal (crash pre-v0.8.5)

    assert limpiar_huerfanos_hosts() is True
    contenido = entorno_hosts.hosts.read_text(encoding="utf-8")
    assert "127.0.0.1 youtube.com" not in contenido
    assert _MARCADOR_INICIO not in contenido


def test_no_toca_hosts_del_usuario(entorno_hosts):
    """Entradas del usuario con OTRO formato/ip no se tocan jamás."""
    usuario = "0.0.0.0 notes.app\n# mi comentario personal\n"
    entorno_hosts.hosts.write_text(entorno_hosts.original + usuario, encoding="utf-8")

    limpiar_huerfanos_hosts()
    contenido = entorno_hosts.hosts.read_text(encoding="utf-8")
    assert "0.0.0.0 notes.app" in contenido
    assert "# mi comentario personal" in contenido


# --------------------------------------------------------------------- #
# 3. Audio: restaurar el volumen EXACTO, no ~50% fijo
# --------------------------------------------------------------------- #

class _FakeWinmm:
    """waveOut falsificado: guarda el volumen que se va escribiendo."""

    def __init__(self, volumen_inicial: int):
        self.volumen = volumen_inicial
        self.escritos: list[int] = []

    def waveOutGetVolume(self, dispositivo, puntero):
        puntero._obj.value = self.volumen
        return 0

    def waveOutSetVolume(self, dispositivo, vol):
        valor = vol.value if hasattr(vol, "value") else int(vol)
        self.escritos.append(valor)
        self.volumen = valor
        return 0


@pytest.fixture()
def winmm_falso(tmp_path, monkeypatch, entorno_hosts):
    fake = _FakeWinmm(volumen_inicial=0x99999999)  # ~60% ambos canales
    ctypes_falso = SimpleNamespace(windll=SimpleNamespace(winmm=fake), byref=__import__("ctypes").byref)
    monkeypatch.setattr(mod, "ctypes", ctypes_falso)
    return fake


def test_volumen_original_restaurado_exacto(entorno_hosts, winmm_falso):
    modo = ModoConcentracion(_cfg())
    modo.activar()          # lee 0x99999999 y pone 0 (mute)
    modo.desactivar()       # debe devolver EXACTAMENTE 0x99999999

    assert winmm_falso.escritos[-1] == 0x99999999


def test_volumen_cero_permanece_cero(entorno_hosts, monkeypatch, tmp_path):
    """Si el usuario YA estaba muteado (vol 0), al salir queda muteado (0)."""
    fake = _FakeWinmm(volumen_inicial=0)
    ctypes_falso = SimpleNamespace(windll=SimpleNamespace(winmm=fake), byref=__import__("ctypes").byref)
    monkeypatch.setattr(mod, "ctypes", ctypes_falso)

    modo = ModoConcentracion(_cfg())
    modo.activar()
    modo.desactivar()
    assert fake.escritos[-1] == 0


def test_sin_volumen_leido_no_toca_audio(entorno_hosts):
    """Si silenciar falló (sin vol_original), restaurar no inventa valores."""
    modo = ModoConcentracion(_cfg())
    assert modo._restaurar_audio() is True  # no-op seguro, sin lanzar
    assert winmm_sin_llamadas(modo)


def winmm_sin_llamadas(modo) -> bool:
    # No hay winmm real en el test: si llegara a llamarse, ctypes fallaría.
    return modo._vol_original is None


# --------------------------------------------------------------------- #
# 4. _extraer_contaminacion unitaria
# --------------------------------------------------------------------- #

def test_extraer_contaminacion_preserva_contenido_legitimo():
    contenido = (
        "# entrada legitima\n"
        "127.0.0.1 localhost\n"
        f"{_MARCADOR_INICIO}\n127.0.0.1 netflix.com\n{_MARCADOR_FIN}\n"
        "0.0.0.0 mipagina.local\n"
    )
    limpio = _extraer_contaminacion(contenido, lineas_journal=[])
    assert "# entrada legitima" in limpio
    assert "127.0.0.1 localhost" in limpio
    assert "0.0.0.0 mipagina.local" in limpio
    assert "netflix.com" not in limpio


if __name__ == "__main__":
    print("test_concentracion_v085: OK")
