"""Avatar OpenPets: la cara bonita sin escribir TypeScript (v0.6.0).

OpenPets (`github.com/OpenPetsHQ/openpets`, MIT) publica un **IPC local**
documentado: un Named Pipe (o un socket/TCP) con autenticación por token y
mensajes JSON de una línea. Este módulo habla ese protocolo desde Python:

    descubrimiento  %APPDATA%\\OpenPets\\runtime\\ipc.json  (endpoint + token)
    transporte      \\\\.\\pipe\\openpets-<hex>-<pid>  |  unix socket  |  tcp://
    petición        {id, version:1, token, method, params}\\n
    respuesta       {ok:true, result} | {ok:false, error:{code,message}}

Solo se usan tres métodos: ``hello`` (disponibilidad), ``pet.react`` (estado)
y ``pet.say`` (burbuja). No hay capturas ni red: todo va por el pipe local.

Degradación: si OpenPets no está abierto, ``iniciar()`` devuelve False y el
motor usa la mascota tkinter. Los envíos van por una cola y un hilo propio:
un OpenPets colgado nunca bloquea la vigilancia.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from yourfocusguard.avatar.base import (
    limpiar_frase,
    reaccion_para_alerta,
    reaccion_para_estado,
)

log = logging.getLogger(__name__)

PROTOCOLO = "openpets-ipc"
VERSION = 1
MAX_MENSAJE = 16 * 1024


class OpenPetsError(Exception):
    """Fallo de transporte o respuesta de error del host."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje


# --------------------------------------------------------------------------- #
# Descubrimiento
# --------------------------------------------------------------------------- #

def ruta_discovery() -> Path:
    """Ruta del archivo de descubrimiento que escribe la app."""
    forzada = os.environ.get("OPENPETS_DISCOVERY_FILE", "").strip()
    if forzada:
        return Path(forzada)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "OpenPets" / "runtime" / "ipc.json"
    if os.uname().sysname == "Darwin":  # pragma: no cover - macOS
        return Path.home() / "Library" / "Application Support" / "OpenPets" / "runtime" / "ipc.json"
    xdg = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if xdg:
        return Path(xdg) / "openpets" / "ipc.json"  # pragma: no cover
    return Path.home() / ".config" / "OpenPets" / "runtime" / "ipc.json"  # pragma: no cover


def leer_discovery(ruta: Path | None = None) -> dict:
    """Lee y valida el archivo de descubrimiento (nunca devuelve basura)."""
    ruta = Path(ruta) if ruta else ruta_discovery()
    try:
        if ruta.stat().st_size > MAX_MENSAJE:
            raise OpenPetsError("invalid_discovery", "archivo demasiado grande")
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise OpenPetsError("unavailable", f"no existe {ruta}")
    except (OSError, json.JSONDecodeError) as exc:
        raise OpenPetsError("invalid_discovery", str(exc))

    if not isinstance(datos, dict):
        raise OpenPetsError("invalid_discovery", "se esperaba un objeto")
    if datos.get("protocol") != PROTOCOLO or datos.get("protocolVersion") != VERSION:
        raise OpenPetsError("invalid_discovery", "protocolo/versión inesperados")
    token = datos.get("token")
    endpoint = datos.get("endpoint")
    if not isinstance(token, str) or not 16 <= len(token) <= 256:
        raise OpenPetsError("invalid_discovery", "token inválido")
    if not isinstance(endpoint, str) or not endpoint or "\0" in endpoint:
        raise OpenPetsError("invalid_discovery", "endpoint inválido")
    if not isinstance(datos.get("pid"), int):
        raise OpenPetsError("invalid_discovery", "pid inválido")
    return datos


# --------------------------------------------------------------------------- #
# Transporte
# --------------------------------------------------------------------------- #

def _con_timeout(funcion: Callable[[], bytes], segundos: float) -> bytes:
    """Ejecuta el intercambio con deadline; un pipe colgado no nos cuelga."""
    resultado: dict[str, Any] = {}

    def _trabajo() -> None:
        try:
            resultado["valor"] = funcion()
        except Exception as exc:  # se re-lanza en el hilo que llama
            resultado["error"] = exc

    hilo = threading.Thread(target=_trabajo, name="yfg-ipc", daemon=True)
    hilo.start()
    hilo.join(segundos)
    if hilo.is_alive():
        raise OpenPetsError("timeout", "OpenPets no respondió a tiempo")
    if "error" in resultado:
        raise resultado["error"]
    return resultado.get("valor", b"")


def _intercambio(endpoint: str, linea: bytes, timeout: float) -> bytes:
    if endpoint.startswith("tcp://"):
        return _intercambio_tcp(endpoint, linea, timeout)
    if endpoint.startswith("\\\\") or endpoint.startswith("\\\\.\\pipe\\"):
        return _intercambio_pipe(endpoint, linea, timeout)
    return _intercambio_unix(endpoint, linea, timeout)


def _leer_hasta_salto(conexion, buffer: bytes, timeout: float) -> bytes:
    limite = time.monotonic() + timeout
    while b"\n" not in buffer and time.monotonic() < limite:
        trozo = conexion.recv(65536)
        if not trozo:
            break
        buffer += trozo
        if len(buffer) > MAX_MENSAJE:
            raise OpenPetsError("response_too_large", "respuesta demasiado grande")
    return buffer


def _intercambio_tcp(endpoint: str, linea: bytes, timeout: float) -> bytes:
    resto = endpoint[len("tcp://"):]
    host, _, puerto = resto.rpartition(":")
    if not host or not puerto.isdigit():
        raise OpenPetsError("invalid_discovery", f"endpoint tcp inválido: {endpoint!r}")
    with socket.create_connection((host, int(puerto)), timeout=timeout) as conexion:
        conexion.settimeout(timeout)
        conexion.sendall(linea)
        return _leer_hasta_salto(conexion, b"", timeout)


def _intercambio_unix(endpoint: str, linea: bytes, timeout: float) -> bytes:
    if not hasattr(socket, "AF_UNIX"):  # pragma: no cover - Windows viejo
        raise OpenPetsError("unsupported", "sockets unix no disponibles")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conexion:  # pragma: no cover
        conexion.settimeout(timeout)
        conexion.connect(endpoint)
        conexion.sendall(linea)
        return _leer_hasta_salto(conexion, b"", timeout)


def _intercambio_pipe(endpoint: str, linea: bytes, timeout: float) -> bytes:
    try:
        import win32file  # noqa: F401  (pywin32)
    except ImportError:
        return _intercambio_pipe_stdlib(endpoint, linea, timeout)
    import pywintypes
    import win32file
    import win32pipe

    handle = win32file.CreateFile(
        endpoint,
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        0,
        None,
        win32file.OPEN_EXISTING,
        0,
        None,
    )
    try:
        # PIPE_NOWAIT + sondeo: así el deadline del hilo externo sí sirve.
        win32pipe.SetNamedPipeHandleState(handle, win32pipe.PIPE_NOWAIT, None, None)
        win32file.WriteFile(handle, linea)
        buffer = b""
        limite = time.monotonic() + timeout
        while b"\n" not in buffer and time.monotonic() < limite:
            try:
                _, trozo = win32file.ReadFile(handle, 65536)
            except pywintypes.error as exc:
                if getattr(exc, "winerror", None) == 232:  # ERROR_NO_DATA
                    time.sleep(0.02)
                    continue
                raise
            buffer += trozo
            if len(buffer) > MAX_MENSAJE:
                raise OpenPetsError("response_too_large", "respuesta demasiado grande")
        return buffer
    finally:
        try:
            handle.Close()
        except Exception:  # pragma: no cover
            pass


def _intercambio_pipe_stdlib(endpoint: str, linea: bytes, timeout: float) -> bytes:
    """Sin pywin32: `open()` sobre el pipe. Bloquea, pero corre en su hilo."""
    archivo = open(endpoint, "r+b", buffering=0)
    try:
        archivo.write(linea)
        buffer = b""
        while b"\n" not in buffer:
            trozo = archivo.read(4096)
            if not trozo:
                break
            buffer += trozo
        return buffer
    finally:
        archivo.close()


def peticion(
    discovery: dict | None,
    method: str,
    params: dict | None = None,
    timeout: float = 2.0,
) -> Any:
    """Envía una petición al IPC y devuelve ``result`` (lanza si falla)."""
    datos = discovery or leer_discovery()
    solicitud = {
        "id": uuid.uuid4().hex,
        "version": VERSION,
        "token": datos["token"],
        "method": method,
        "params": params or {},
    }
    linea = (json.dumps(solicitud, ensure_ascii=False) + "\n").encode("utf-8")
    if len(linea) > MAX_MENSAJE:
        raise OpenPetsError("request_too_large", "petición demasiado grande")

    try:
        crudo = _con_timeout(
            lambda: _intercambio(datos["endpoint"], linea, timeout), timeout + 0.5
        )
    except OpenPetsError:
        raise
    except Exception as exc:  # TimeoutError, OSError, pipes ocupados…
        raise OpenPetsError("unavailable", str(exc) or type(exc).__name__)
    primera = crudo.split(b"\n", 1)[0]
    if not primera:
        raise OpenPetsError("empty_response", "OpenPets cerró sin responder")
    try:
        respuesta = json.loads(primera.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenPetsError("invalid_response", str(exc))
    if not isinstance(respuesta, dict):
        raise OpenPetsError("invalid_response", "se esperaba un objeto")
    if respuesta.get("ok") is True:
        return respuesta.get("result")
    error = respuesta.get("error") or {}
    raise OpenPetsError(
        str(error.get("code") or "request_failed"),
        str(error.get("message") or "OpenPets rechazó la petición"),
    )


# --------------------------------------------------------------------------- #
# El avatar
# --------------------------------------------------------------------------- #

class AvatarOpenPets:
    """Cara OpenPets con cola propia: el motor nunca se bloquea por el pipe."""

    nombre = "openpets"

    def __init__(
        self,
        cfg=None,
        enviar: Callable[[dict | None, str, dict | None], Any] | None = None,
        discovery: dict | None = None,
    ) -> None:
        self.cfg = cfg
        self.disponible = False
        self.frases = True if cfg is None else bool(getattr(cfg.avatar, "frases", True))
        self._enviar = enviar or peticion
        self._discovery = discovery
        self._cola: "queue.Queue[tuple[str, dict] | None]" = queue.Queue(maxsize=32)
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._ultima_reaccion: str | None = None
        self._errores_seguidos = 0
        self._silencio_hasta = 0.0

    # -- ciclo de vida -------------------------------------------------- #

    def iniciar(self) -> bool:
        """Comprueba que OpenPets responde (`hello`) y arranca el hilo."""
        if self.disponible:
            return True
        try:
            self._enviar(self._discovery, "hello", {})
        except Exception as exc:
            log.info("OpenPets no disponible: %s", exc)
            return False
        self.disponible = True
        self._hilo = threading.Thread(
            target=self._bucle, name="yfg-avatar-openpets", daemon=True
        )
        self._hilo.start()
        log.info("avatar OpenPets conectado")
        return True

    def parar(self) -> None:
        self._parar.set()
        try:
            self._cola.put_nowait(None)
        except queue.Full:
            pass
        if self._hilo is not None:
            self._hilo.join(timeout=1.5)
            self._hilo = None
        self.disponible = False

    # -- API del motor -------------------------------------------------- #

    def fijar_estado(self, estado: str, detalle: str = "") -> None:
        reaccion = reaccion_para_estado(estado)
        if reaccion == self._ultima_reaccion:
            return
        self._ultima_reaccion = reaccion
        self._encolar("pet.react", {"reaction": reaccion})

    def al_alerta(self, nivel: int, mensaje: str) -> None:
        if not self.frases:
            return
        frase = limpiar_frase(mensaje)
        if not frase:
            return
        self._encolar(
            "pet.say",
            {"message": frase, "reaction": reaccion_para_alerta(nivel)},
        )

    def preguntar(self, texto: str, opciones=()) -> None:
        """Burbuja con la pregunta. Los botones solo existen en la mascota tk.

        Con OpenPets se responde con los atajos (Ctrl+Alt+F11/F10) o la CLI;
        el Pet Assistant añadirá voz y chat en la Fase 3.
        """
        self.al_alerta(1, texto)

    def respuestas(self) -> list[str]:
        return []

    # -- interno -------------------------------------------------------- #

    def _encolar(self, method: str, params: dict) -> None:
        try:
            self._cola.put_nowait((method, params))
        except queue.Full:
            log.debug("cola del avatar llena: se descarta %s", method)

    def _bucle(self) -> None:
        while not self._parar.is_set():
            elemento = self._cola.get()
            if elemento is None:
                return
            method, params = elemento
            if time.monotonic() < self._silencio_hasta:
                continue
            try:
                self._enviar(self._discovery, method, params)
                self._errores_seguidos = 0
            except Exception as exc:
                self._errores_seguidos += 1
                log.debug("avatar OpenPets %s falló: %s", method, exc)
                if self._errores_seguidos >= 3:
                    # OpenPets se cerró o reinició: 60 s de silencio y a
                    # releer el descubrimiento en el siguiente intento.
                    self._errores_seguidos = 0
                    self._silencio_hasta = time.monotonic() + 60
                    self._discovery = None
