"""Tests unitarios para el Scheduler de recordatorios y rutinas (v0.8.3 Fase 3)."""
from __future__ import annotations

import time
from yourfocusguard.config import RutinasCfg
from yourfocusguard.core.scheduler import Scheduler, extraer_recordatorio_voz


def test_extraer_recordatorio_voz():
    # Minutos
    ok, tarea, mins = extraer_recordatorio_voz("recuérdame en 30 minutos preparar la comida")
    assert ok is True
    assert tarea == "Preparar la comida"
    assert mins == 30.0

    # Media hora
    ok, tarea, mins = extraer_recordatorio_voz("recuerda en media hora llamar al cliente")
    assert ok is True
    assert tarea == "Llamar al cliente"
    assert mins == 30.0

    # Horas
    ok, tarea, mins = extraer_recordatorio_voz("avísame en 2 horas salir al banco")
    assert ok is True
    assert tarea == "Salir al banco"
    assert mins == 120.0

    # Abreviado
    ok, tarea, mins = extraer_recordatorio_voz("recuerdame en 15 min tomar agua")
    assert ok is True
    assert tarea == "Tomar agua"
    assert mins == 15.0

    # Frase sin recordatorio
    ok, tarea, mins = extraer_recordatorio_voz("hola einstein, cómo estás")
    assert ok is False


def test_scheduler_programar_y_verificar(cfg):
    scheduler = Scheduler(cfg)

    # Programar en 0.001 min (~0.06s)
    rec = scheduler.programar("Prueba rápida", delta_minutos=0.0001)
    assert rec.disparado is False

    # Inmediatamente antes del tiempo
    time.sleep(0.02)
    avisos = scheduler.verificar_pendientes()
    assert len(avisos) == 1
    assert "Prueba rápida" in avisos[0]

    # Al volver a verificar ya está consumido
    avisos2 = scheduler.verificar_pendientes()
    assert len(avisos2) == 0


def test_scheduler_rutina_pausa_activa(cfg):
    cfg.rutinas = RutinasCfg(
        habilitado=True,
        pausa_activa_cada_min=0.0001,  # disparo inmediato en test
        pausa_activa_mensaje="Estira y toma agua",
    )
    scheduler = Scheduler(cfg)
    scheduler._ultimo_check_rutina = time.time() - 10.0  # simular tiempo pasado

    avisos = scheduler.verificar_pendientes()
    assert any("Estira y toma agua" in a for a in avisos)


def test_scheduler_pausa_activa_no_dispara_si_inactivo(cfg):
    cfg.rutinas = RutinasCfg(
        habilitado=True,
        pausa_activa_cada_min=50.0,
        pausa_activa_mensaje="Llevas 50 minutos concentrado.",
    )
    scheduler = Scheduler(cfg)
    # Simular 1 hora (3600s) de ausencia/inactividad (en_foco=False)
    avisos = scheduler.verificar_pendientes(delta_seg=3600.0, en_foco=False)
    assert len(avisos) == 0
    assert scheduler.segundos_foco_acumulados == 0.0

    # Ahora el usuario vuelve y trabaja 50 minutos (3000s) con en_foco=True
    avisos2 = scheduler.verificar_pendientes(delta_seg=3000.0, en_foco=True)
    assert len(avisos2) == 1
    assert "50 minutos concentrado" in avisos2[0]

