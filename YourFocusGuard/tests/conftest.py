"""Fixtures compartidas: configuración real del proyecto + carpeta de datos temporal."""
from __future__ import annotations

import itertools
import os
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from yourfocusguard.config import load_config  # noqa: E402

# Carpeta temporal local del proyecto. `pytest` usa el TEMP del sistema, que en
# algunos entornos con sandbox de archivos (p. ej. el agente DSH) no es
# listable; un directorio dentro del repositorio siempre funciona y no cambia
# el comportamiento de los tests.
# El nombre lleva el PID: si la limpieza falla, la corrida siguiente no reusa
# una base de datos vieja.
_BASE_TMP = RAIZ / "_pytmp" / "casos"
_CASOS = itertools.count()
shutil.rmtree(_BASE_TMP, ignore_errors=True)


@pytest.fixture()
def tmp_path():
    """Sustituye el tmp_path de pytest por uno dentro del proyecto."""
    ruta = _BASE_TMP / f"caso{os.getpid()}_{next(_CASOS)}"
    ruta.mkdir(parents=True, exist_ok=True)
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


@pytest.fixture()
def cfg(tmp_path):
    """Configuración del perfil pc con datos redirigidos a tmp.

    v0.5.0: el `config/` se COPIA a tmp (sin el `user.toml` personal). Antes
    los tests leían y escribían el `config/` del proyecto: correr la suite te
    cambiaba la configuración real (de hecho activaba la captura de pantalla).
    """
    config_dir = tmp_path / "config"
    shutil.copytree(RAIZ / "config", config_dir)
    (config_dir / "user.toml").unlink(missing_ok=True)
    c = load_config(
        perfil="pc", config_dir=config_dir, datos_carpeta=str(tmp_path / "data")
    )
    # v0.3.0: los tests no abren ventanas de escritorio; la mascota real
    # se prueba en Windows (run.py mascota --demo). Aquí va desactivada.
    c.mascota.visible = False
    # v0.4.0: por defecto el agente corre en Modo Anclado (captura apagada).
    # La mayoría de tests ejercita el pipeline clásico: lo re-encendemos
    # aquí; el Modo Anclado tiene sus propios tests (test_anclado.py).
    c.captura.habilitada = True
    return c


@pytest.fixture()
def cfg_laptop(tmp_path):
    config_dir = tmp_path / "config"
    shutil.copytree(RAIZ / "config", config_dir)
    (config_dir / "user.toml").unlink(missing_ok=True)
    c = load_config(
        perfil="laptop", config_dir=config_dir, datos_carpeta=str(tmp_path / "data")
    )
    c.mascota.visible = False
    c.captura.habilitada = True
    return c
