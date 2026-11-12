"""Avatar (v0.6.0): mapeo OpenPets, IPC simulado y fábrica con degradación."""
from __future__ import annotations

import json
import time

import pytest

from yourfocusguard.avatar import (
    REACCIONES_OPENPETS,
    crear_avatar,
    limpiar_frase,
    reaccion_para_alerta,
    reaccion_para_estado,
)
from yourfocusguard.avatar.openpets import (
    AvatarOpenPets,
    OpenPetsError,
    leer_discovery,
)


def _esperar(condicion, limite=2.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(0.01)
    return False


# --------------------------------------------------------------------------- #
# Mapeo y frases
# --------------------------------------------------------------------------- #

def test_cada_estado_tiene_una_reaccion_valida():
    for estado in ("EN_ESPERA", "FOCO", "ESCALADA", "COOLDOWN", "PAUSA", "DETENIDO"):
        assert reaccion_para_estado(estado) in REACCIONES_OPENPETS
    assert reaccion_para_estado("FOCO") == "working"
    assert reaccion_para_estado("PAUSA") == "waiting"
    assert reaccion_para_estado("ESCALADA") == "error"
    assert reaccion_para_estado("cualquiera") == "idle"


def test_reaccion_de_alerta_distingue_aviso_de_llamado():
    assert reaccion_para_alerta(0) == "thinking"
    assert reaccion_para_alerta(1) == "thinking"
    assert reaccion_para_alerta(2) == "error"


def test_limpiar_frase_una_linea_sin_urls_y_acotada():
    assert limpiar_frase("Hola\n\n  mundo\t ") == "Hola mundo"
    assert "http" not in limpiar_frase("mira https://ejemplo.com/x y vuelve")
    larga = "a" * 300
    limpia = limpiar_frase(larga, maximo=20)
    assert len(limpia) == 20 and limpia.endswith("…")
    assert limpiar_frase("") == ""


# --------------------------------------------------------------------------- #
# Descubrimiento
# --------------------------------------------------------------------------- #

def _escribir_discovery(tmp_path, **cambios):
    datos = {
        "protocolVersion": 1,
        "protocol": "openpets-ipc",
        "endpoint": "\\\\.\\pipe\\openpets-abc-123",
        "token": "x" * 32,
        "appVersion": "3.0.0",
        "pid": 4321,
        "platform": "win32",
    }
    datos.update(cambios)
    ruta = tmp_path / "ipc.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def test_lee_un_descubrimiento_valido(tmp_path):
    datos = leer_discovery(_escribir_discovery(tmp_path))
    assert datos["endpoint"].startswith("\\\\.\\pipe\\openpets-")
    assert datos["token"] == "x" * 32


def test_rechaza_descubrimiento_ajeno(tmp_path):
    with pytest.raises(OpenPetsError):
        leer_discovery(_escribir_discovery(tmp_path, protocol="otra-cosa"))
    with pytest.raises(OpenPetsError):
        leer_discovery(_escribir_discovery(tmp_path, token="corto"))
    with pytest.raises(OpenPetsError):
        leer_discovery(tmp_path / "no-existe.json")


# --------------------------------------------------------------------------- #
# Cliente IPC (sin sockets: se inyecta el envío)
# --------------------------------------------------------------------------- #

class EnvioFake:
    def __init__(self, falla=False):
        self.llamadas = []
        self.falla = falla

    def __call__(self, discovery, method, params):
        if self.falla:
            raise OpenPetsError("unavailable", "OpenPets apagado")
        self.llamadas.append((method, params))
        return {"ok": True}


def test_avatar_envia_hello_react_y_say(cfg):
    envio = EnvioFake()
    avatar = AvatarOpenPets(cfg, enviar=envio, discovery={"token": "t" * 20})
    assert avatar.iniciar() is True
    assert envio.llamadas[0][0] == "hello"

    avatar.fijar_estado("FOCO")
    avatar.fijar_estado("FOCO")          # repetido: no se reenvía
    avatar.al_alerta(2, "¿qué haces?\n vuelve")
    assert _esperar(lambda: len(envio.llamadas) >= 3)
    avatar.parar()

    metodos = [m for m, _ in envio.llamadas]
    assert metodos.count("pet.react") == 1
    say = [p for m, p in envio.llamadas if m == "pet.say"][0]
    assert say["message"] == "¿qué haces? vuelve"
    assert say["reaction"] == "error"


def test_avatar_sin_openpets_no_arranca(cfg):
    avatar = AvatarOpenPets(cfg, enviar=EnvioFake(falla=True))
    assert avatar.iniciar() is False
    assert avatar.disponible is False
    avatar.parar()  # no rompe


def test_avatar_preguntar_es_una_burbuja_sin_botones(cfg):
    envio = EnvioFake()
    avatar = AvatarOpenPets(cfg, enviar=envio, discovery={"token": "t" * 20})
    avatar.iniciar()
    avatar.preguntar("¿Necesitas una pausa?", [("sigo", "Sigo")])
    assert _esperar(lambda: len(envio.llamadas) >= 2)
    avatar.parar()
    assert envio.llamadas[-1][0] == "pet.say"
    assert avatar.respuestas() == []


# --------------------------------------------------------------------------- #
# Transporte real (TCP loopback, el mismo framing que el pipe)
# --------------------------------------------------------------------------- #

def test_peticion_tcp_punta_a_punta():
    import socket
    import threading

    from yourfocusguard.avatar.openpets import peticion

    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    puerto = servidor.getsockname()[1]
    visto: dict = {}

    def servir():
        conexion, _ = servidor.accept()
        datos = b""
        while b"\n" not in datos:
            datos += conexion.recv(4096)
        visto.update(json.loads(datos.split(b"\n")[0].decode("utf-8")))
        conexion.sendall(b'{"id":"r1","ok":true,"result":{"ok":true}}\n')
        conexion.close()

    hilo = threading.Thread(target=servir, daemon=True)
    hilo.start()
    discovery = {
        "protocol": "openpets-ipc",
        "protocolVersion": 1,
        "endpoint": f"tcp://127.0.0.1:{puerto}",
        "token": "t" * 32,
    }
    resultado = peticion(discovery, "hello", {})
    hilo.join(2)
    servidor.close()

    assert resultado == {"ok": True}
    assert visto["method"] == "hello"
    assert visto["token"] == "t" * 32
    assert visto["version"] == 1
    assert visto["params"] == {}
    assert visto["id"]


def test_flujo_completo_con_openpets_simulado(cfg, tmp_path, monkeypatch):
    """Descubrimiento -> fábrica -> hello/react/say por el socket real."""
    import socket
    import threading

    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(8)
    puerto = servidor.getsockname()[1]
    recibidas: list[dict] = []

    def atender(total=3):
        for _ in range(total):
            conexion, _ = servidor.accept()
            datos = b""
            while b"\n" not in datos:
                trozo = conexion.recv(4096)
                if not trozo:
                    break
                datos += trozo
            if b"\n" in datos:
                recibidas.append(json.loads(datos.split(b"\n")[0].decode("utf-8")))
            conexion.sendall(b'{"id":"r","ok":true,"result":{"ok":true}}\n')
            conexion.close()

    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()

    ruta = tmp_path / "ipc.json"
    ruta.write_text(
        json.dumps(
            {
                "protocolVersion": 1,
                "protocol": "openpets-ipc",
                "endpoint": f"tcp://127.0.0.1:{puerto}",
                "token": "t" * 32,
                "appVersion": "3.0.0",
                "pid": 99,
                "platform": "win32",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENPETS_DISCOVERY_FILE", str(ruta))
    cfg.avatar.proveedor = "auto"
    cfg.mascota.visible = True

    avatar = crear_avatar(cfg)
    assert isinstance(avatar, AvatarOpenPets)   # no cayó a la mascota
    avatar.fijar_estado("FOCO")
    avatar.al_alerta(2, "Vuelve a Lightroom")
    assert _esperar(lambda: len(recibidas) >= 3)
    avatar.parar()
    hilo.join(2)
    servidor.close()

    metodos = [r["method"] for r in recibidas]
    assert metodos[:3] == ["hello", "pet.react", "pet.say"]
    assert recibidas[1]["params"] == {"reaction": "working"}
    assert "Vuelve a Lightroom" in recibidas[2]["params"]["message"]


def test_peticion_sin_respuesta_agota_el_tiempo():
    import socket
    import threading

    from yourfocusguard.avatar.openpets import peticion

    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    puerto = servidor.getsockname()[1]
    liberar = threading.Event()

    def aceptar_y_callar():
        conexion, _ = servidor.accept()
        liberar.wait(3)
        conexion.close()

    threading.Thread(target=aceptar_y_callar, daemon=True).start()
    discovery = {
        "endpoint": f"tcp://127.0.0.1:{puerto}",
        "token": "t" * 32,
    }
    try:
        with pytest.raises(OpenPetsError):
            peticion(discovery, "hello", {}, timeout=0.3)
    finally:
        liberar.set()
        servidor.close()


# --------------------------------------------------------------------------- #
# Fábrica: auto / openpets / tk / ninguno
# --------------------------------------------------------------------------- #

class MascotaFalsa:
    nombre = "tk"

    def __init__(self, cfg=None):
        self.iniciado = 0
        self.disponible = True

    def iniciar(self):
        self.iniciado += 1
        return True

    def fijar_estado(self, estado, detalle=""):
        pass

    def al_alerta(self, nivel, mensaje):
        pass

    def preguntar(self, texto, opciones=()):
        pass

    def respuestas(self):
        return []

    def parar(self):
        pass


def test_auto_cae_a_la_mascota_si_openpets_no_responde(cfg, monkeypatch):
    import yourfocusguard.avatar.openpets as openpets_mod
    import yourfocusguard.mascota as mascota_mod

    monkeypatch.setattr(
        openpets_mod.AvatarOpenPets, "iniciar", lambda self: False
    )
    monkeypatch.setattr(mascota_mod, "Mascota", MascotaFalsa)
    cfg.avatar.proveedor = "auto"
    cfg.mascota.visible = True

    avatar = crear_avatar(cfg)
    assert isinstance(avatar, MascotaFalsa)


def test_openpets_configurado_no_cae_a_tk(cfg, monkeypatch):
    import yourfocusguard.avatar.openpets as openpets_mod

    monkeypatch.setattr(
        openpets_mod.AvatarOpenPets, "iniciar", lambda self: False
    )
    cfg.avatar.proveedor = "openpets"
    assert crear_avatar(cfg) is None


def test_proveedor_ninguno(cfg):
    cfg.avatar.proveedor = "ninguno"
    assert crear_avatar(cfg) is None


def test_proveedor_tk_y_mascota_oculta(cfg, monkeypatch):
    import yourfocusguard.mascota as mascota_mod

    monkeypatch.setattr(mascota_mod, "Mascota", MascotaFalsa)
    cfg.avatar.proveedor = "tk"
    cfg.mascota.visible = True
    assert isinstance(crear_avatar(cfg), MascotaFalsa)
    cfg.mascota.visible = False
    assert crear_avatar(cfg) is None


# --------------------------------------------------------------------------- #
# Integración con el motor
# --------------------------------------------------------------------------- #

def test_el_motor_usa_la_fabrica_de_avatar(cfg, monkeypatch):
    import yourfocusguard.avatar as avatar_mod
    from yourfocusguard.brain.router import BrainRouter
    from yourfocusguard.engine import Agent
    from yourfocusguard.storage.db import EventDB

    creado = MascotaFalsa()
    monkeypatch.setattr(avatar_mod, "crear_avatar", lambda cfg: creado)

    db = EventDB(cfg.ruta_db)
    agente = Agent(
        cfg, db, BrainRouter(cfg), mascota="auto", consola=False, hotkey=False,
        bloqueo_fn=lambda: False,
    )
    assert agente.mascota is creado
    agente.sesion_id = db.abrir_sesion("pc_diseno", "")
    agente._escribir_estado(1_000_000.0)
    db.cerrar()
