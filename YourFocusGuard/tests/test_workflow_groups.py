"""Tests para workflow_groups y config_writer (v0.8.0)."""
import time
from pathlib import Path
from yourfocusguard.workflow_groups import (
    GrupoFlujo,
    GestorFlujos,
    DetectorDescubrimiento,
)
from yourfocusguard.config_writer import agregar_app_relacionada_en_toml


def test_grupo_flujo_matcheo():
    grupo = GrupoFlujo(
        nombre="edicion_foto",
        apps=["lightroom", "photoshop"],
        apps_relacionadas=["gutoflow", "bridge"],
        tolerancia_seg=120.0,
        mensaje_aviso="¿Volvemos a Lightroom?",
    )

    assert grupo.matchea_principal("Adobe Lightroom Classic") is True
    assert grupo.matchea_principal("Photoshop") is True
    assert grupo.matchea_principal("Gutoflow") is False

    assert grupo.matchea_relacionada("Gutoflow.exe") is True
    assert grupo.matchea_relacionada("Bridge") is True
    assert grupo.matchea_relacionada("Spotify") is False


def test_gestor_flujos_tolerancia():
    grupo = GrupoFlujo(
        nombre="edicion_foto",
        apps=["lightroom"],
        apps_relacionadas=["gutoflow"],
        tolerancia_seg=60.0,
    )
    gestor = GestorFlujos([grupo])

    t0 = 1000.0
    # Primer segundo en Gutoflow: relacionada, no supera tolerancia
    v1 = gestor.evaluar("Gutoflow", grupo, t0)
    assert v1.es_relacionada is True
    assert v1.supera_tolerancia is False
    assert v1.segundos_en_relacionada == 0.0

    # 30s después: aún dentro de tolerancia
    v2 = gestor.evaluar("Gutoflow", grupo, t0 + 30.0)
    assert v2.es_relacionada is True
    assert v2.supera_tolerancia is False
    assert v2.segundos_en_relacionada == 30.0

    # 65s después: supera tolerancia
    v3 = gestor.evaluar("Gutoflow", grupo, t0 + 65.0)
    assert v3.es_relacionada is True
    assert v3.supera_tolerancia is True
    assert "Gutoflow" in v3.mensaje


def test_detector_descubrimiento_disparo():
    grupo = GrupoFlujo(
        nombre="edicion_foto",
        apps=["lightroom"],
        apps_relacionadas=["gutoflow"],
    )
    detector = DetectorDescubrimiento(umbral_seg=120.0, cooldown_seg=600.0)

    t0 = 2000.0
    # App desconocida durante 10s: no dispara
    ev1 = detector.evaluar("CapCut", grupo, t0)
    assert ev1 is None

    ev2 = detector.evaluar("CapCut", grupo, t0 + 10.0)
    assert ev2 is None

    # App desconocida supera 120s: dispara pregunta
    ev3 = detector.evaluar("CapCut", grupo, t0 + 125.0)
    assert ev3 is not None
    assert ev3.app == "capcut"
    assert "CapCut" in ev3.pregunta
    assert "edicion_foto" in ev3.pregunta

    # Cooldown inmediato: no vuelve a disparar
    ev4 = detector.evaluar("CapCut", grupo, t0 + 130.0)
    assert ev4 is None


def test_config_writer_agregar_relacionada(tmp_path: Path):
    ruta_toml = tmp_path / "user.toml"
    contenido_inicial = """[sesion]
apps = ["lightroom"]

[[flujos.grupo]]
nombre = "edicion_foto"
apps = ["lightroom"]
apps_relacionadas = ["bridge"]
"""
    ruta_toml.write_text(contenido_inicial, encoding="utf-8")

    # Agregar Gutoflow al grupo edicion_foto
    ok = agregar_app_relacionada_en_toml(ruta_toml, "edicion_foto", "Gutoflow")
    assert ok is True

    texto_nuevo = ruta_toml.read_text(encoding="utf-8")
    assert "gutoflow" in texto_nuevo
    assert "bridge" in texto_nuevo
