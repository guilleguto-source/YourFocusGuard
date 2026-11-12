"""Tests unitarios para el buzón de notas rápidas (Brain Dump Logseq / Markdown)."""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from yourfocusguard.actions.groq_voice import es_intencion_nota
from yourfocusguard.storage.vault import guardar_nota_rapida, resolver_archivo_destino


def test_es_intencion_nota():
    assert es_intencion_nota("Anota investigar el plugin de lightroom") is True
    assert es_intencion_nota("Apunta comprar café") is True
    assert es_intencion_nota("Idea: reordenar la interfaz") is True
    assert es_intencion_nota("Recordar llamar al doctor") is True
    assert es_intencion_nota("No olvidar enviar el correo") is True
    assert es_intencion_nota("Hola, ¿cómo estás hoy?") is False
    assert es_intencion_nota("Estoy muy cansado, qué hago") is False
    assert es_intencion_nota("") is False


def test_guardar_nota_en_carpeta_diario_logseq(tmp_path, cfg):
    journals_dir = tmp_path / "logseq_journals"
    journals_dir.mkdir()
    cfg.notas.carpeta_diario = str(journals_dir)

    exito, mensaje, ruta = guardar_nota_rapida("Anota investigar nueva paleta de color", cfg=cfg)

    assert exito is True
    assert ruta.is_file()
    assert ruta.parent == journals_dir
    nombre_esperado = datetime.datetime.now().strftime("%Y_%m_%d.md")
    assert ruta.name == nombre_esperado

    contenido = ruta.read_text(encoding="utf-8")
    assert "- TODO " in contenido
    assert "Investigar nueva paleta de color" in contenido


def test_guardar_nota_fallback_inbox(tmp_path, cfg):
    cfg.notas.carpeta_diario = ""
    inbox_file = tmp_path / "inbox_tdah.md"
    cfg.notas.archivo_inbox_respaldo = str(inbox_file)

    exito, mensaje, ruta = guardar_nota_rapida("Idea: probar atajo ctrl shift p", cfg=cfg)

    assert exito is True
    assert ruta == inbox_file
    contenido = inbox_file.read_text(encoding="utf-8")
    assert "Probar atajo ctrl shift p" in contenido


def test_guardar_nota_vacia_rechazada():
    exito, mensaje, ruta = guardar_nota_rapida("   ")
    assert exito is False
    assert "vacío" in mensaje.lower()
