"""Pruebas del esquema SQLite del Apéndice B + migración 001."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from yourfocusguard.storage.db import EventDB, SCHEMA_VERSION


def test_esquema_y_version(tmp_path):
    db = EventDB(tmp_path / "a.db")
    version = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    columnas = {r[1] for r in db._conn.execute("PRAGMA table_info(evento)")}
    assert {"accion_sugerida", "origen"} <= columnas  # migración 001
    db.cerrar()


def test_sesion_y_eventos(tmp_path):
    db = EventDB(tmp_path / "a.db")
    sid = db.abrir_sesion("pc_diseno", "Escribir tesis")
    db.insertar_evento(sid, "FOCO", "deteccion", motivo="ninguno", confianza=0.8,
                       accion="nada", origen="heuristica")
    db.insertar_evento(sid, "ESCALADA", "desvio", motivo="video", confianza=0.85,
                       accion_sugerida="aviso", origen="nube:gemini")
    db.cerrar_sesion(sid, ciclos=3)

    fila = sqlite3.connect(tmp_path / "a.db").execute(
        "SELECT maquina, ciclos, fin_ts FROM sesion WHERE id = ?", (sid,)
    ).fetchone()
    assert fila[0] == "pc_diseno" and fila[1] == 3 and fila[2]

    recientes = EventDB(tmp_path / "a.db").eventos_recientes(2)
    assert recientes[0]["tipo"] == "desvio"
    assert recientes[0]["origen"] == "nube:gemini"
    assert recientes[0]["prompt_id"] == "v1"


def test_resumen_hoy_cuenta_latidos_y_alertas(tmp_path):
    db = EventDB(tmp_path / "a.db")
    sid = db.abrir_sesion("pc_diseno")
    for estado in ("FOCO", "FOCO", "ESCALADA"):
        db.insertar_evento(sid, estado, "deteccion", accion="nada")
    db.insertar_evento(sid, "ESCALADA", "alerta", accion="toast")
    db.insertar_evento(sid, "ESCALADA", "alerta", accion="voz")
    db.insertar_evento(sid, "FOCO", "desvio")
    resumen = db.resumen_hoy()
    assert resumen["minutos_estado"] == {"FOCO": 2, "ESCALADA": 1}
    assert resumen["alertas"] == {"toast": 1, "voz": 1}
    assert resumen["desvios"] == 1
    db.cerrar()


def test_eventos_de_ayer_no_cuentan_hoy(tmp_path):
    db = EventDB(tmp_path / "a.db")
    sid = db.abrir_sesion("pc_diseno")
    ayer = (datetime.now() - timedelta(days=1)).astimezone().isoformat(timespec="seconds")
    db.insertar_evento(sid, "FOCO", "deteccion", ts=ayer)
    assert db.resumen_hoy()["eventos_total"] == 0
    db.cerrar()


def test_presupuesto_acumula_por_dia(tmp_path):
    db = EventDB(tmp_path / "a.db")
    db.registrar_llamada_api(0.003)
    llamadas, coste = db.registrar_llamada_api(0.003)
    assert llamadas == 2
    assert abs(coste - 0.006) < 1e-9
    assert abs(db.presupuesto_hoy() - 0.006) < 1e-9
    db.cerrar()


def test_poda_por_retencion(tmp_path):
    db = EventDB(tmp_path / "a.db")
    sid = db.abrir_sesion("pc_diseno")
    viejo = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%S")
    db.insertar_evento(sid, "FOCO", "deteccion", ts=viejo)
    db.insertar_evento(sid, "FOCO", "deteccion")  # ahora
    borrados = db.podar(180)
    assert borrados == 1
    assert db.resumen_hoy()["eventos_total"] == 1
    db.cerrar()


def test_exportar_csv(tmp_path):
    db = EventDB(tmp_path / "a.db")
    sid = db.abrir_sesion("pc_diseno")
    db.insertar_evento(sid, "ESCALADA", "alerta", motivo="video", accion="voz")
    ruta = tmp_path / "export.csv"
    n = db.exportar_csv(ruta, dias=7)
    assert n == 1
    contenido = ruta.read_text(encoding="utf-8-sig")
    assert "accion" in contenido and "voz" in contenido
    db.cerrar()


def test_purgar_todo(tmp_path):
    db = EventDB(tmp_path / "a.db")
    sid = db.abrir_sesion("pc_diseno")
    db.insertar_evento(sid, "FOCO", "deteccion")
    db.registrar_llamada_api(0.003)
    db.purgar_todo()
    assert db.resumen_hoy()["eventos_total"] == 0
    assert db.presupuesto_hoy() == 0.0
    db.cerrar()


def test_segunda_apertura_es_idempotente(tmp_path):
    EventDB(tmp_path / "a.db").cerrar()
    db = EventDB(tmp_path / "a.db")  # no debe romper por columnas duplicadas
    db.insertar_evento(db.abrir_sesion("laptop"), "FOCO", "deteccion")
    db.cerrar()


def test_consumo_voz_y_resumen_semanal(tmp_path):
    db = EventDB(tmp_path / "a.db")
    sid = db.abrir_sesion("laptop", tarea="Programar asistente")

    # Insertar eventos de foco y desvío
    db.insertar_evento(sid, "FOCO", "deteccion", app="vscode")
    db.insertar_evento(sid, "FOCO", "deteccion", app="vscode")
    db.insertar_evento(sid, "ESCALADA", "desvio", app="chrome", motivo="youtube")
    db.insertar_evento(sid, "ESCALADA", "alerta", accion="voz")

    # Registrar consumo de voz
    llamadas, coste, seg_voz, tok_voz = db.registrar_consumo_voz(
        segundos_audio=12.5, tokens_llm=45, coste_estimado=0.0005
    )
    assert llamadas == 1
    assert abs(seg_voz - 12.5) < 1e-5
    assert tok_voz == 45
    assert abs(coste - 0.0005) < 1e-5

    # Consultar resumen semanal
    rep = db.resumen_semanal(dias=7)
    assert rep["dias"] == 7
    assert rep["total_desvios"] == 1
    assert len(rep["top_apps_distraccion"]) == 1
    assert rep["top_apps_distraccion"][0] == ("chrome", 1)
    assert rep["escaladas"].get("voz") == 1
    assert rep["sesiones_total"] >= 1
    assert abs(rep["segundos_voz_semanal"] - 12.5) < 1e-5
    assert rep["tokens_voz_semanal"] == 45

    db.cerrar()
