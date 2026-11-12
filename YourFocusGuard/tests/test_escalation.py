"""Pruebas de la escalera de alertas (tabla 5): tiempos, cooldown y tope horario."""
from __future__ import annotations

from yourfocusguard.actions.escalation import EscalationLadder
from yourfocusguard.constants import Accion

T0 = 1_000_000.0


def _ladder(cfg):
    return EscalationLadder(cfg.alertas)


def test_tiempos_exactos_de_la_escalera(cfg):
    lad = _ladder(cfg)
    assert lad.begin(T0)

    assert [a.nivel for a in lad.tick(T0 + 10, 0.2)] == []           # nada todavía
    assert [a.nivel for a in lad.tick(T0 + 20, 0.3)] == [0]           # mascota
    assert [a.nivel for a in lad.tick(T0 + 30, 0.5)] == [1]           # aviso sutil
    assert [a.nivel for a in lad.tick(T0 + 45, 0.75)] == []           # entre tramos
    assert [a.nivel for a in lad.tick(T0 + 60, 1.0)] == [2]           # toast
    assert [a.nivel for a in lad.tick(T0 + 90, 1.5)] == [3]           # voz
    # la voz arranca el cooldown: silencio 5 min
    assert lad.en_cooldown(T0 + 91)
    assert [a.nivel for a in lad.tick(T0 + 200, 3.3)] == []


def test_niveles_acumulados_en_un_solo_tick(cfg):
    """Si el motor tarda (captura cada 15 s), varios niveles salen juntos."""
    lad = _ladder(cfg)
    lad.begin(T0)
    alertas = lad.tick(T0 + 35, 0.6)
    assert [a.nivel for a in alertas] == [0, 1]


def test_cooldown_terminado_abre_nuevo_ciclo(cfg):
    lad = _ladder(cfg)
    lad.begin(T0)
    for nivel in (0, 1, 2, 3):
        lad.tick(T0 + 90, 1.5)
    assert lad.en_cooldown(T0 + 300)

    alertas = lad.tick(T0 + 400, 6.6)  # cooldown venció en T0+390
    assert alertas == []                # ciclo nuevo: aún sin niveles
    assert [a.nivel for a in lad.tick(T0 + 421, 7.0)] == [0]
    assert [a.nivel for a in lad.tick(T0 + 431, 7.2)] == [1]


def test_tope_por_hora(cfg):
    eventos = []
    lad = EscalationLadder(cfg.alertas, on_event=lambda t, m: eventos.append((t, m)))
    for i in range(4):
        assert lad.begin(T0 + i * 400) is True
        lad.end(T0 + i * 400 + 60)
    # 4 ciclos en menos de una hora: el 5.º no se permite
    assert lad.begin(T0 + 4 * 400) is False
    assert lad.silencioso
    assert ("alerta", "tope_horario") in eventos


def test_tope_se_libera_al_pasar_la_hora(cfg):
    lad = _ladder(cfg)
    for i in range(4):
        lad.begin(T0 + i * 100)
        lad.end(T0 + i * 100 + 60)
    assert lad.begin(T0 + 400) is False
    assert lad.begin(T0 + 3_700) is True  # los primeros ciclos ya expiraron


def test_end_cierra_y_resume(cfg):
    lad = _ladder(cfg)
    lad.begin(T0)
    lad.tick(T0 + 35, 0.6)
    resumen = lad.end(T0 + 120)
    assert resumen is not None
    assert resumen.niveles_disparados == [0, 1]
    assert abs(resumen.duracion_min - 2.0) < 0.01
    assert not lad.activo
    assert lad.tick(T0 + 121, 2.0) == []
    assert lad.end(T0 + 122) is None


def test_mensajes_llevan_minutos_y_tarea(cfg):
    lad = _ladder(cfg)
    lad.begin(T0)
    alertas = lad.tick(T0 + 30, 0.7, motivo="redes", tarea="Escribir tesis")
    a1 = alertas[-1]                    # N0 y N1 salen juntos; el texto está en N1
    assert a1.accion == Accion.AVISO
    assert "1 min" in a1.mensaje
    a2 = lad.tick(T0 + 60, 3.0, motivo="video", tarea="Escribir tesis")[0]
    assert "Escribir tesis" in a2.mensaje
    assert a2.accion == Accion.TOAST
    a3 = lad.tick(T0 + 90, 5.0, motivo="video", tarea="")[0]
    assert a3.texto_voz and "5 minutos" in a3.texto_voz
    assert "Escribir tesis" not in a3.texto_voz
