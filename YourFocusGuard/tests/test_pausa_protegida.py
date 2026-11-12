import pytest
from yourfocusguard.constants import Estado
from tests.test_engine import montar, RelojFalso, VentanaGuion


def test_pausa_protegida_no_reanuda_sin_confirmacion(cfg):
    reloj = RelojFalso(1_700_000_000.0)
    ventana = VentanaGuion([("code.exe", "proyecto - VSCode")])
    agente, db, _, _ = montar(cfg, reloj, ventana)
    agente.estado = Estado.FOCO

    # 1. Iniciar pausa protegida de 10 min
    agente.paused_until = reloj.t + 600.0
    agente._pausa_espera_confirmacion = True

    # Durante la pausa (minuto 5)
    reloj.avanzar(300.0)
    r = agente._tick(reloj.t)
    assert r["estado"] == "PAUSA"
    assert agente.paused_until is not None

    # Pasados los 10 minutos (minuto 10 + 1s): no debe auto-reanudar
    reloj.avanzar(301.0)
    r_vencido = agente._tick(reloj.t)
    assert r_vencido["estado"] == "PAUSA"
    assert agente.paused_until is not None
    assert agente._pausa_espera_confirmacion is True

    # 2. Confirmación explícita del usuario
    agente._responder_pregunta("continuar", reloj.t)
    assert agente.paused_until is None
    assert agente._pausa_espera_confirmacion is False
    assert agente.estado == Estado.FOCO
    db.cerrar()


def test_sugerencia_pausa_30min_enfoque(cfg):
    reloj = RelojFalso(1000.0)
    ventana = VentanaGuion([("code.exe", "proyecto - VSCode")])
    agente, db, _, _ = montar(cfg, reloj, ventana)
    agente.estado = Estado.FOCO

    # Arranca conteo
    agente._comprobar_refuerzo_positivo(reloj.t)
    assert agente._foco_continuo_desde == reloj.t
    assert not agente._foco_30min_sugerido

    # Avanzar 30 minutos continuos (1805 seg)
    reloj.avanzar(1805.0)
    agente._comprobar_refuerzo_positivo(reloj.t)
    assert agente._foco_30min_sugerido is True

    filas = db.eventos_recientes(10)
    assert any("30_min_foco_sugerencia_pausa" in (f["motivo"] or "") for f in filas)
    db.cerrar()
