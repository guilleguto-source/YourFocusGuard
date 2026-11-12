"""Base de eventos y sesiones: esquema del Apéndice B del blueprint.

Esquema v1 (letra del blueprint): tablas ``evento`` y ``sesion``.
Migración 001 (sprint 1): columnas ``accion_sugerida`` y ``origen`` en
``evento`` + tabla ``consumo_api`` para el presupuesto diario. El Apéndice B
exige que cada cambio de esquema sea una migración numerada.
Migración 002 (v0.3.0): tabla ``presupuesto`` — segundos por patrón y fecha
para los presupuestos diarios de las prohibiciones ("no permitir YouTube
más de 1 h"). ``PRAGMA user_version`` lleva el número actual (3).

Lo que NUNCA se guarda: imágenes. Los eventos guardan decisiones, no
evidencia visual (cap. 7 del blueprint).
"""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from yourfocusguard.constants import HEARTBEAT_SEG, PROMPT_ID_V1

log = logging.getLogger(__name__)

SCHEMA_VERSION = 4


def _ahora_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _hoy_prefijo() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class EventDB:
    """Acceso a SQLite con WAL (la consola ``status`` lee mientras el agente escribe)."""

    def __init__(self, ruta: Path) -> None:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta = ruta
        self._conn = sqlite3.connect(str(ruta), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def cerrar(self) -> None:
        try:
            self._conn.commit()
            self._conn.close()
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------ #
    # Esquema y migraciones
    # ------------------------------------------------------------------ #

    def _init_schema(self) -> None:
        conn = self._conn
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS evento (
              id             INTEGER PRIMARY KEY AUTOINCREMENT,
              ts             TEXT    NOT NULL,   -- ISO 8601 local
              sesion_id      TEXT    NOT NULL,
              estado         TEXT    NOT NULL,   -- FOCO | PAUSA | ESCALADA | COOLDOWN | EN_ESPERA
              tipo           TEXT    NOT NULL,   -- desvio | alerta | pausa | retoma | deteccion | ...
              motivo         TEXT,
              app_activa     TEXT,
              titulo_ventana TEXT,
              confianza      REAL,
              accion         TEXT,               -- nada | mascota | aviso | toast | voz
              prompt_id      TEXT    NOT NULL,
              accion_sugerida TEXT,              -- migración 001
              origen          TEXT               -- migración 001
            );

            CREATE TABLE IF NOT EXISTS sesion (
              id          TEXT PRIMARY KEY,
              maquina     TEXT NOT NULL,
              inicio_ts   TEXT NOT NULL,
              fin_ts      TEXT,
              tarea       TEXT,
              ciclos      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS consumo_api (
              fecha          TEXT PRIMARY KEY,
              llamadas       INTEGER NOT NULL DEFAULT 0,
              coste_estimado REAL    NOT NULL DEFAULT 0.0,
              segundos_voz   REAL    DEFAULT 0.0,
              tokens_voz     INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS presupuesto (   -- migración 002 (v0.3.0)
              fecha    TEXT    NOT NULL,               -- AAAA-MM-DD
              patron   TEXT    NOT NULL,               -- p. ej. "youtube"
              segundos INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (fecha, patron)
            );

            CREATE INDEX IF NOT EXISTS idx_evento_ts ON evento(ts);
            CREATE INDEX IF NOT EXISTS idx_evento_sesion ON evento(sesion_id);
            """
        )
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < SCHEMA_VERSION:
            # Base v1 sin las columnas de la migración 001
            for columna in ("accion_sugerida", "origen"):
                try:
                    conn.execute(f"ALTER TABLE evento ADD COLUMN {columna} TEXT")
                except sqlite3.OperationalError:
                    pass  # ya existía
            # Migración 004 (v0.8.2): trazabilidad de voz en consumo_api
            for columna, tipo in (("segundos_voz", "REAL DEFAULT 0.0"), ("tokens_voz", "INTEGER DEFAULT 0")):
                try:
                    conn.execute(f"ALTER TABLE consumo_api ADD COLUMN {columna} {tipo}")
                except sqlite3.OperationalError:
                    pass  # ya existía
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()

    # ------------------------------------------------------------------ #
    # Sesiones
    # ------------------------------------------------------------------ #

    def abrir_sesion(self, maquina: str, tarea: str = "") -> str:
        sesion_id = uuid.uuid4().hex[:12]
        self._conn.execute(
            "INSERT INTO sesion (id, maquina, inicio_ts, tarea) VALUES (?,?,?,?)",
            (sesion_id, maquina, _ahora_iso(), tarea or None),
        )
        self._conn.commit()
        return sesion_id

    def cerrar_sesion(self, sesion_id: str, ciclos: int = 0) -> None:
        self._conn.execute(
            "UPDATE sesion SET fin_ts = ?, ciclos = ? WHERE id = ?",
            (_ahora_iso(), ciclos, sesion_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Eventos
    # ------------------------------------------------------------------ #

    def insertar_evento(
        self,
        sesion_id: str,
        estado: str,
        tipo: str,
        motivo: str | None = None,
        app: str | None = None,
        titulo: str | None = None,
        confianza: float | None = None,
        accion: str | None = None,
        accion_sugerida: str | None = None,
        origen: str | None = None,
        prompt_id: str = PROMPT_ID_V1,
        ts: str | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO evento
               (ts, sesion_id, estado, tipo, motivo, app_activa, titulo_ventana,
                confianza, accion, prompt_id, accion_sugerida, origen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ts or _ahora_iso(),
                sesion_id,
                estado,
                tipo,
                motivo,
                app,
                (titulo or "")[:160] or None,
                confianza,
                accion,
                prompt_id,
                accion_sugerida,
                origen,
            ),
        )
        self._conn.commit()

    def eventos_recientes(self, n: int = 8) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM evento ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()

    # ------------------------------------------------------------------ #
    # Latidos y resumen del día
    # ------------------------------------------------------------------ #

    def resumen_hoy(self) -> dict:
        """Agregados del día para el comando ``status`` (aproximados por latidos)."""
        prefijo = _hoy_prefijo()
        filas = self._conn.execute(
            "SELECT estado, tipo, accion, confianza FROM evento WHERE ts LIKE ?",
            (f"{prefijo}%",),
        ).fetchall()

        minutos_estado: dict[str, int] = {}
        conteo_tipos: dict[str, int] = {}
        alertas: dict[str, int] = {}
        for fila in filas:
            if fila["tipo"] == "deteccion":
                minutos_estado[fila["estado"]] = (
                    minutos_estado.get(fila["estado"], 0) + HEARTBEAT_SEG // 60
                )
            conteo_tipos[fila["tipo"]] = conteo_tipos.get(fila["tipo"], 0) + 1
            if fila["tipo"] == "alerta" and fila["accion"]:
                alertas[fila["accion"]] = alertas.get(fila["accion"], 0) + 1

        ultima = self._conn.execute(
            "SELECT ts FROM evento ORDER BY id DESC LIMIT 1"
        ).fetchone()

        return {
            "minutos_estado": minutos_estado,
            "tipos": conteo_tipos,
            "alertas": alertas,
            "desvios": conteo_tipos.get("desvio", 0),
            "retomas": conteo_tipos.get("retoma", 0),
            "eventos_total": len(filas),
            "ultima_actividad": ultima["ts"] if ultima else None,
        }

    def resumen_semanal(self, dias: int = 7) -> dict:
        """Agregados de los últimos `dias` para el reporte semanal F5."""
        desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S")
        filas = self._conn.execute(
            """SELECT ts, estado, tipo, motivo, app_activa, titulo_ventana, accion
               FROM evento WHERE ts >= ? ORDER BY id""",
            (desde,),
        ).fetchall()

        minutos_foco_dia: dict[str, int] = {}
        minutos_estado: dict[str, int] = {}
        conteo_desvios_app: dict[str, int] = {}
        conteo_alertas: dict[str, int] = {}
        motivos_desvio: dict[str, int] = {}

        for fila in filas:
            ts_dia = fila["ts"][:10]
            st = fila["estado"]
            tp = fila["tipo"]
            app = fila["app_activa"] or "desconocida"
            accion = fila["accion"]
            motivo = fila["motivo"]

            if tp == "deteccion":
                minutos_estado[st] = minutos_estado.get(st, 0) + (HEARTBEAT_SEG // 60)
                if st == "FOCO":
                    minutos_foco_dia[ts_dia] = minutos_foco_dia.get(ts_dia, 0) + (HEARTBEAT_SEG // 60)
            elif tp == "desvio":
                conteo_desvios_app[app] = conteo_desvios_app.get(app, 0) + 1
                if motivo:
                    motivos_desvio[motivo] = motivos_desvio.get(motivo, 0) + 1
            elif tp == "alerta" and accion:
                conteo_alertas[accion] = conteo_alertas.get(accion, 0) + 1

        top_distracciones = sorted(conteo_desvios_app.items(), key=lambda x: x[1], reverse=True)[:5]

        # Sesiones completadas en el periodo
        sesiones = self._conn.execute(
            "SELECT count(*) as total, coalesce(sum(ciclos), 0) as ciclos FROM sesion WHERE inicio_ts >= ?",
            (desde,),
        ).fetchone()

        # Consumo acumulado de API y voz
        desde_fecha = desde[:10]
        consumo = self._conn.execute(
            """SELECT coalesce(sum(llamadas), 0) as llamadas,
                      coalesce(sum(coste_estimado), 0.0) as coste,
                      coalesce(sum(segundos_voz), 0.0) as segundos_voz,
                      coalesce(sum(tokens_voz), 0) as tokens_voz
               FROM consumo_api WHERE fecha >= ?""",
            (desde_fecha,),
        ).fetchone()

        return {
            "dias": dias,
            "desde": desde,
            "minutos_foco_total": minutos_estado.get("FOCO", 0),
            "minutos_pausa_total": minutos_estado.get("PAUSA", 0),
            "minutos_foco_por_dia": minutos_foco_dia,
            "minutos_por_estado": minutos_estado,
            "total_desvios": sum(conteo_desvios_app.values()),
            "top_apps_distraccion": top_distracciones,
            "escaladas": conteo_alertas,
            "motivos_desvio": sorted(motivos_desvio.items(), key=lambda x: x[1], reverse=True)[:5],
            "sesiones_total": sesiones["total"] if sesiones else 0,
            "pomodoros_completados": sesiones["ciclos"] if sesiones else 0,
            "coste_api_semanal": consumo["coste"] if consumo else 0.0,
            "segundos_voz_semanal": consumo["segundos_voz"] if consumo else 0.0,
            "tokens_voz_semanal": consumo["tokens_voz"] if consumo else 0,
        }

    # ------------------------------------------------------------------ #
    # Presupuesto de API
    # ------------------------------------------------------------------ #

    def registrar_llamada_api(self, coste_estimado: float) -> tuple[int, float]:
        hoy = _hoy_prefijo()
        self._conn.execute(
            """INSERT INTO consumo_api (fecha, llamadas, coste_estimado)
               VALUES (?, 1, ?)
               ON CONFLICT(fecha) DO UPDATE SET
                 llamadas = llamadas + 1,
                 coste_estimado = coste_estimado + excluded.coste_estimado""",
            (hoy, coste_estimado),
        )
        self._conn.commit()
        fila = self._conn.execute(
            "SELECT llamadas, coste_estimado FROM consumo_api WHERE fecha = ?",
            (hoy,),
        ).fetchone()
        return (fila["llamadas"], fila["coste_estimado"])

    def registrar_consumo_voz(
        self,
        segundos_audio: float = 0.0,
        tokens_llm: int = 0,
        coste_estimado: float = 0.0,
    ) -> tuple[int, float, float, int]:
        hoy = _hoy_prefijo()
        self._conn.execute(
            """INSERT INTO consumo_api (fecha, llamadas, coste_estimado, segundos_voz, tokens_voz)
               VALUES (?, 1, ?, ?, ?)
               ON CONFLICT(fecha) DO UPDATE SET
                 llamadas = llamadas + 1,
                 coste_estimado = coste_estimado + excluded.coste_estimado,
                 segundos_voz = coalesce(segundos_voz, 0.0) + excluded.segundos_voz,
                 tokens_voz = coalesce(tokens_voz, 0) + excluded.tokens_voz""",
            (hoy, coste_estimado, segundos_audio, tokens_llm),
        )
        self._conn.commit()
        fila = self._conn.execute(
            "SELECT llamadas, coste_estimado, coalesce(segundos_voz, 0.0) as segundos_voz, coalesce(tokens_voz, 0) as tokens_voz FROM consumo_api WHERE fecha = ?",
            (hoy,),
        ).fetchone()
        return (fila["llamadas"], fila["coste_estimado"], fila["segundos_voz"], fila["tokens_voz"])

    def presupuesto_hoy(self) -> float:
        fila = self._conn.execute(
            "SELECT coste_estimado FROM consumo_api WHERE fecha = ?",
            (_hoy_prefijo(),),
        ).fetchone()
        return fila["coste_estimado"] if fila else 0.0

    # ------------------------------------------------------------------ #
    # Presupuestos de prohibiciones (migración 002, v0.3.0)
    # ------------------------------------------------------------------ #

    def presupuesto_sumar(self, patron: str, segundos: int) -> int:
        """Acumula segundos de primer plano para un patrón; devuelve el total hoy."""
        if segundos <= 0 or not patron:
            return self.presupuesto_usado_hoy(patron)
        self._conn.execute(
            """INSERT INTO presupuesto (fecha, patron, segundos)
               VALUES (?, ?, ?)
               ON CONFLICT(fecha, patron) DO UPDATE SET
                 segundos = segundos + excluded.segundos""",
            (_hoy_prefijo(), patron, int(segundos)),
        )
        self._conn.commit()
        return self.presupuesto_usado_hoy(patron)

    def presupuesto_usado_hoy(self, patron: str) -> int:
        fila = self._conn.execute(
            "SELECT segundos FROM presupuesto WHERE fecha = ? AND patron = ?",
            (_hoy_prefijo(), patron),
        ).fetchone()
        return fila["segundos"] if fila else 0

    def presupuestos_hoy(self) -> dict[str, int]:
        """{patron: segundos usados hoy} — para el panel y `status`."""
        filas = self._conn.execute(
            "SELECT patron, segundos FROM presupuesto WHERE fecha = ?",
            (_hoy_prefijo(),),
        ).fetchall()
        return {fila["patron"]: fila["segundos"] for fila in filas}

    # ------------------------------------------------------------------ #
    # Poda, purga y exportación
    # ------------------------------------------------------------------ #

    def podar(self, retencion_dias: int) -> int:
        """Borra eventos más antiguos que la retención (tabla 7: 6 meses)."""
        limite = (datetime.now() - timedelta(days=retencion_dias)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        cursor = self._conn.execute(
            "DELETE FROM evento WHERE ts < ?", (limite,)
        )
        # Los presupuestos de prohibiciones también caducan con la retención
        limite_fecha = (datetime.now() - timedelta(days=retencion_dias)).strftime(
            "%Y-%m-%d"
        )
        self._conn.execute(
            "DELETE FROM presupuesto WHERE fecha < ?", (limite_fecha,)
        )
        self._conn.commit()
        if cursor.rowcount:
            log.info("poda automática: %d eventos eliminados", cursor.rowcount)
        return cursor.rowcount

    def purgar_todo(self) -> None:
        for tabla in ("evento", "sesion", "consumo_api", "presupuesto"):
            self._conn.execute(f"DELETE FROM {tabla}")
        self._conn.commit()

    def exportar_csv(self, ruta: Path, dias: int = 7) -> int:
        """Exporta los últimos N días a CSV con cabeceras en español."""
        desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S")
        filas = self._conn.execute(
            """SELECT ts, estado, tipo, motivo, app_activa, titulo_ventana,
                      confianza, accion, accion_sugerida, origen
               FROM evento WHERE ts >= ? ORDER BY id""",
            (desde,),
        ).fetchall()
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig para que Excel muestre bien acentos al hacer doble clic
        with ruta.open("w", newline="", encoding="utf-8-sig") as fh:
            escritor = csv.writer(fh)
            escritor.writerow(
                [
                    "fecha_hora", "estado", "tipo", "motivo", "app_activa",
                    "titulo_ventana", "confianza", "accion", "accion_sugerida",
                    "origen",
                ]
            )
            for fila in filas:
                escritor.writerow([fila[k] for k in fila.keys()])
        return len(filas)
