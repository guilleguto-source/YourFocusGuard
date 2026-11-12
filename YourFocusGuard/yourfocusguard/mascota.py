"""Mascota agente: la guardiana de escritorio (v0.3.0).

Ventana tkinter siempre-visible, sin marco y con fondo transparente en
Windows, que refleja el estado del agente en tiempo real:

    EN_ESPERA / DETENIDO -> dormido   (ojos cerrados, z z z)
    FOCO                -> atento     (ojos abiertos, sonrisa)
    ESCALADA            -> alerta     (ojos grandes, anillo, rebota)
    COOLDOWN            -> descanso   (ojos entrecerrados)
    PAUSA               -> pausa      (ojos entrecerrados + taza)

Los avisos de la escalera aparecen como burbuja de texto sobre su cabeza
4 segundos. Un clic la abre el Panel del Guardián; se puede arrastrar.

¿Se puede cambiar la apariencia? Sí, por TEMAS (clasico | oscuro | calido):
elegirlo desde el panel o [mascota] tema = "..." en user.toml. Añadir un
tema nuevo = copiar un dict en TEMAS con tus colores. vPet (Steam) puede
coexistir como decoración, pero no es controlable desde el agente.

Diseño resistente: si no hay tkinter o no hay escritorio (tests, SSH,
servidor), la mascota se desactiva con un aviso y el agente sigue igual.
El hilo de Tk es propio; el motor le habla por una cola (thread-safe).
"""
from __future__ import annotations

import logging
import queue
import threading
import webbrowser
from typing import Callable

from yourfocusguard.config import Config

log = logging.getLogger(__name__)

TEMAS: dict[str, dict] = {
    "clasico": {
        "cuerpo": "#D8D2C4",   # greige cálido
        "tinta": "#2F2B25",    # contorno y ojos
        "placa": "#F1EDE4",    # brillos (blanco de ojos)
        "realce": "#7A8B6F",   # salvia: zzz / anillo / taza
        "clave": "#F1F1F2",    # color-transparente de fondo (Windows)
    },
    "oscuro": {
        "cuerpo": "#2E2C28",
        "tinta": "#EDE9DF",
        "placa": "#3A3831",
        "realce": "#9DBBA8",
        "clave": "#F1F1F2",
    },
    "calido": {
        "cuerpo": "#E6D5BB",   # beige
        "tinta": "#4A3F33",
        "placa": "#F6F2E9",
        "realce": "#C1543F",   # terracota
        "clave": "#F1F1F2",
    },
}

#: estado interno del agente -> sprite + texto humano
_ESTADO_A_SPRITE = {
    "EN_ESPERA": ("dormido", "esperando señal"),
    "FOCO": ("atento", "enfocada"),
    "PAUSA": ("pausa", "en pausa"),
    "ESCALADA": ("alerta", "¡a otra cosa!"),
    "COOLDOWN": ("descanso", "descansando"),
    "DETENIDO": ("dormido", "detenida"),
}

_aviso_una_vez = False


class Mascota:
    """Guardiana de escritorio. Todo es opcional: si no puede abrir ventana,
    queda como objeto inerte que traga eventos sin romper nada."""

    nombre = "tk"  # v0.6.0: identifica la cara activa (ver avatar/)

    def __init__(self, cfg: Config, reloj: Callable | None = None) -> None:
        self.cfg = cfg
        self.disponible = False
        self._cola: queue.Queue = queue.Queue()
        self._hilo: threading.Thread | None = None
        self._parar_evento = threading.Event()
        self._panel_url = f"http://127.0.0.1:{cfg.panel.puerto}"
        self._ultimo: tuple | None = None
        # v0.5.0: respuestas del usuario a las preguntas del asistente.
        # La lista la escribe el hilo de Tk y la lee el motor (GIL: append y
        # copia son atómicos para este uso).
        self._respuestas: list[str] = []
        self._ventana_pregunta = None

    # ------------------------------------------------------------------ #
    # API del motor (thread-safe, nunca lanza)
    # ------------------------------------------------------------------ #

    def iniciar(self) -> bool:
        """Arranca el hilo de Tk. Devuelve True si el hilo vive (aunque la
        ventana puede fallar después: mira ``disponible``)."""
        if self._hilo is not None:
            return self.disponible
        self._hilo = threading.Thread(
            target=self._run, name="yfg-mascota", daemon=True
        )
        self._hilo.start()
        # dar un instante a Tk para saber si hay escritorio
        self._hilo.join(timeout=1.5)
        return self.disponible

    def fijar_estado(self, estado: str, detalle: str = "") -> None:
        payload = ("estado", str(estado), str(detalle or ""))
        if payload == self._ultimo:
            return  # sin cambios: no despertamos a Tk
        self._ultimo = payload
        try:
            self._cola.put(payload)
        except Exception:  # pragma: no cover
            pass

    def al_alerta(self, nivel: int, mensaje: str) -> None:
        try:
            self._cola.put(("alerta", int(nivel), str(mensaje or "")[:90]))
        except Exception:  # pragma: no cover
            pass

    def preguntar(self, texto: str, opciones) -> None:
        """Muestra la pregunta con botones de respuesta (v0.5.0).

        ``opciones`` es una lista de (clave, etiqueta). Al pulsar un botón, la
        clave queda en ``respuestas()`` para que el motor la recoja en el
        siguiente ciclo.
        """
        try:
            self._cola.put(
                ("preguntar", str(texto or ""), tuple(opciones or ()))
            )
        except Exception:  # pragma: no cover
            pass

    def respuestas(self) -> list[str]:
        """Devuelve y vacía las respuestas pendientes (thread-safe de hecho)."""
        if not self._respuestas:
            return []
        pendientes = self._respuestas[:]
        self._respuestas.clear()
        return pendientes

    def parar(self) -> None:
        self._parar_evento.set()
        try:
            self._cola.put(("parar",))
        except Exception:  # pragma: no cover
            pass
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)
        self.disponible = False

    # ------------------------------------------------------------------ #
    # Hilo de Tk: el único que toca la ventana
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        global _aviso_una_vez
        try:
            import tkinter as tk
        except Exception as exc:
            if not _aviso_una_vez:
                _aviso_una_vez = True
                log.info("mascota no disponible (sin tkinter: %s)", exc)
            return
        try:
            root = tk.Tk()
        except Exception as exc:
            if not _aviso_una_vez:
                _aviso_una_vez = True
                log.info("mascota no disponible (sin escritorio: %s)", exc)
            return

        try:
            tema = dict(TEMAS.get(self.cfg.mascota.tema) or TEMAS["clasico"])
        except Exception:
            tema = dict(TEMAS["clasico"])

        w = max(90, int(self.cfg.mascota.ancho))
        alto = w + 34
        self._clave = tema["clave"]

        root.title("YourFocusGuard · mascota")
        root.overrideredirect(True)
        try:
            root.attributes("-topmost", True)
        except Exception:  # pragma: no cover
            pass
        try:
            root.attributes("-transparentcolor", self._clave)
        except Exception:
            # tk sin soporte de transparencia (no-Windows): ventana cuadrada
            pass

        try:
            ancho_pantalla = root.winfo_screenwidth()
            alto_pantalla = root.winfo_screenheight()
        except Exception:  # pragma: no cover
            ancho_pantalla, alto_pantalla = 1920, 1080
        margen, barra = 24, 48  # barra: hueco aproximado de la taskbar
        if self.cfg.mascota.posicion == "inferior_izquierda":
            x = margen
        else:
            x = ancho_pantalla - w - margen
        y = alto_pantalla - alto - barra
        root.geometry(f"{w}x{alto}+{x}+{y}")

        lienzo = tk.Canvas(
            root, width=w, height=w, bg=self._clave, highlightthickness=0
        )
        lienzo.pack(fill="both", expand=True)
        self._etiqueta = tk.Label(
            root,
            text="esperando señal",
            fg=tema["tinta"],
            bg=self._clave,
            font=("Segoe UI", 9),
        )
        self._etiqueta.pack(fill="x")

        self._root = root
        self._lienzo = lienzo
        self._tema = tema
        self._w = w
        self._sprite = "dormido"
        self._rebote_arriba = False
        self._base_y = y
        self._arrastrando = None

        # clic: abrir el panel; arrastre: moverla
        lienzo.bind("<Button-1>", self._al_pulsar)
        lienzo.bind("<B1-Motion>", self._al_arrastrar)
        lienzo.bind("<ButtonRelease-1>", self._al_soltar)

        self.disponible = True
        self._dibujar("dormido", "esperando señal")

        def _bomba() -> None:
            if self._parar_evento.is_set():
                try:
                    root.destroy()
                except Exception:  # pragma: no cover
                    pass
                return
            self._procesar()
            self._animar()
            root.after(160, _bomba)

        root.after(160, _bomba)
        try:
            root.mainloop()
        finally:
            self.disponible = False

    # ------------------------------------------------------------------ #

    def _animar(self) -> None:
        """Rebote suave mientras está en alerta."""
        if not self.disponible or self._sprite != "alerta":
            return
        self._rebote_arriba = not self._rebote_arriba
        delta = -5 if self._rebote_arriba else 0
        try:
            partes = self._root.geometry().split("+")
            x0, y0 = int(partes[1]), int(partes[2])
            self._root.geometry(f"+{x0}+{self._base_y + delta}")
        except Exception:  # pragma: no cover
            pass

    def _al_pulsar(self, evento) -> None:
        self._arrastrando = (evento.x_root, evento.y_root)

    def _al_arrastrar(self, evento) -> None:
        if not self._arrastrando:
            return
        try:
            partes = self._root.geometry().split("+")
            x0, y0 = int(partes[1]), int(partes[2])
            dx = evento.x_root - self._arrastrando[0]
            dy = evento.y_root - self._arrastrando[1]
            self._root.geometry(f"+{x0 + dx}+{y0 + dy}")
            self._base_y = y0 + dy
            self._arrastrando = (evento.x_root, evento.y_root)
        except Exception:  # pragma: no cover
            pass

    def _al_soltar(self, evento) -> None:
        fue_click = self._arrastrando is not None and (
            abs(evento.x_root - self._arrastrando[0]) < 4
            and abs(evento.y_root - self._arrastrando[1]) < 4
        )
        self._arrastrando = None
        if fue_click:
            try:
                webbrowser.open(self._panel_url)
            except Exception:  # pragma: no cover
                pass

    # ------------------------------------------------------------------ #
    # Dibujo por sprite (tk.Canvas puro: sin imágenes, tema-able)
    # ------------------------------------------------------------------ #

    def _dibujar(self, sprite: str, texto: str) -> None:
        t = self._tema
        c = self._lienzo
        w = self._w
        try:
            c.delete("all")
        except Exception:  # pragma: no cover
            return
        cuerpo = (int(w * 0.10), int(w * 0.26), int(w * 0.90), int(w * 0.98))
        c.create_oval(
            cuerpo, fill=t["cuerpo"], outline=t["tinta"], width=3
        )
        cx1, cx2 = int(w * 0.34), int(w * 0.66)  # centro de la cara
        cy = int(w * 0.52)

        if sprite == "dormido":
            for dx in (-1, 1):
                c.create_arc(
                    cx1 + dx * int(w * 0.10) - 10, cy - 6,
                    cx1 + dx * int(w * 0.10) + 10, cy + 8,
                    start=200, extent=140, style="arc",
                    outline=t["tinta"], width=3,
                )
            c.create_line(
                cx2 - 6, cy + int(w * 0.16), cx2 + 6, cy + int(w * 0.16),
                fill=t["tinta"], width=3,
            )
            c.create_text(
                w * 0.80, w * 0.16, text="z", fill=t["realce"],
                font=("Segoe UI", 13, "bold"),
            )
            c.create_text(
                w * 0.92, w * 0.06, text="z", fill=t["realce"],
                font=("Segoe UI", 10, "bold"),
            )
        elif sprite == "atento":
            for dx in (-1, 1):
                x = cx2 + dx * int(w * 0.13)
                c.create_oval(
                    x - 9, cy - 9, x + 9, cy + 9,
                    fill=t["placa"], outline=t["tinta"], width=2,
                )
                c.create_oval(
                    x - 4, cy - 4, x + 4, cy + 4, fill=t["tinta"], outline="",
                )
            c.create_arc(
                cx1 - 8, cy + int(w * 0.02), cx2 + 8, cy + int(w * 0.20),
                start=20, extent=140, style="arc",
                outline=t["tinta"], width=3,
            )
        elif sprite == "alerta":
            for dx in (-1, 1):
                x = cx2 + dx * int(w * 0.13)
                c.create_oval(
                    x - 12, cy - 13, x + 12, cy + 13,
                    fill=t["placa"], outline=t["tinta"], width=2,
                )
                c.create_oval(x - 6, cy - 6, x + 6, cy + 6, fill=t["tinta"], outline="")
            c.create_line(
                cx1 - 4, cy - int(w * 0.14), cx1 + 10, cy - int(w * 0.10),
                fill=t["tinta"], width=4,
            )
            c.create_line(
                cx2 + 4, cy - int(w * 0.10), cx2 + 18, cy - int(w * 0.14),
                fill=t["tinta"], width=4,
            )
            c.create_oval(
                int(w * 0.02), int(w * 0.18), int(w * 0.98), int(w * 0.98),
                outline=t["realce"], width=3, dash=(6, 5),
            )
            c.create_text(
                w * 0.5, w * 0.10, text="!", fill=t["realce"],
                font=("Segoe UI", 16, "bold"),
            )
            c.create_line(
                cx2 - 8, cy + int(w * 0.18), cx2 + 8, cy + int(w * 0.18),
                fill=t["tinta"], width=3,
            )
        else:  # pausa / descanso
            for dx in (-1, 1):
                x = cx2 + dx * int(w * 0.13)
                c.create_line(
                    x - 10, cy + 2, x + 10, cy - 2,
                    fill=t["tinta"], width=4,
                )
            # taza al costado
            bx, by = int(w * 0.13), int(w * 0.70)
            c.create_rectangle(
                bx, by, bx + 16, by + 15, fill=t["realce"], outline=t["tinta"], width=2
            )
            c.create_arc(
                bx + 14, by + 2, bx + 26, by + 13, start=-60, extent=180,
                style="arc", outline=t["tinta"], width=2,
            )
            c.create_line(
                bx + 4, by - 6, bx + 7, by + 1, fill=t["tinta"], width=2
            )
            c.create_line(
                bx + 10, by - 8, bx + 12, by - 1, fill=t["tinta"], width=2
            )
        try:
            self._etiqueta.config(text=texto)
        except Exception:  # pragma: no cover
            pass
        self._sprite = sprite

    # ------------------------------------------------------------------ #
    # Consumo de la cola dentro del hilo de Tk
    # ------------------------------------------------------------------ #

    def _procesar(self) -> None:
        """Drena la cola (una llamada por tick de _bomba)."""
        while True:
            try:
                msg = self._cola.get_nowait()
            except queue.Empty:
                return
            try:
                self._manejar(msg)
            except Exception:  # pragma: no cover
                log.exception("la mascota no pudo procesar %r", msg)

    def _manejar(self, msg) -> None:
        tipo = msg[0]
        if tipo == "parar":
            try:
                self._root.destroy()
            except Exception:  # pragma: no cover
                pass
            return
        if tipo == "estado":
            estado, detalle = msg[1], msg[2]
            sprite, texto = _ESTADO_A_SPRITE.get(estado, ("atento", estado.lower()))
            if detalle:
                texto = f"{texto} · {detalle}" if len(detalle) < 26 else detalle[:26]
            self._dibujar(sprite, texto)
            return
        if tipo == "alerta":
            nivel, mensaje = msg[1], msg[2]
            self._burbuja(mensaje or "¡eh, eh!")
            sprite, texto = _ESTADO_A_SPRITE["ESCALADA"]
            self._dibujar("alerta", texto)
            return
        if tipo == "preguntar":
            texto, opciones = msg[1], msg[2]
            self._abrir_pregunta(texto, opciones)
            return

    # ------------------------------------------------------------------ #
    # Pregunta con botones (v0.5.0): el canal de respuesta
    # ------------------------------------------------------------------ #

    def _abrir_pregunta(self, texto: str, opciones) -> None:
        """Ventana pequeña junto a la mascota con hasta tres botones."""
        import tkinter as tk

        self._cerrar_pregunta()
        if not texto:
            return
        t = self._tema
        try:
            ventana = tk.Toplevel(self._root)
            ventana.overrideredirect(True)
            try:
                ventana.attributes("-topmost", True)
            except Exception:  # pragma: no cover
                pass
            ventana.configure(bg=t["placa"])
            marco = tk.Frame(
                ventana, bg=t["placa"], padx=12, pady=10,
                highlightbackground=t["tinta"], highlightthickness=2,
            )
            marco.pack(fill="both", expand=True)
            tk.Label(
                marco, text=texto, wraplength=300, justify="left",
                bg=t["placa"], fg=t["tinta"], font=("Segoe UI", 9),
            ).pack(anchor="w")
            fila = tk.Frame(marco, bg=t["placa"])
            fila.pack(anchor="e", pady=(8, 0))
            for clave, etiqueta in list(opciones)[:3]:
                tk.Button(
                    fila, text=etiqueta, relief="flat", bd=0,
                    bg=t["realce"], fg=t["placa"], activebackground=t["tinta"],
                    padx=10, pady=4, cursor="hand2",
                    command=lambda c=clave: self._responder(c),
                ).pack(side="left", padx=3)
            ventana.update_idletasks()
            ancho = max(260, ventana.winfo_width())
            alto = ventana.winfo_height()
            x = self._root.winfo_x() + self._w // 2 - ancho // 2
            y = self._root.winfo_y() - alto - 10
            ventana.geometry(f"{ancho}x{alto}+{max(0, x)}+{max(0, y)}")
            self._ventana_pregunta = ventana
            self._dibujar("alerta", "¿qué pasa?")
            # si nadie contesta en un minuto, se rinde sola (no insiste)
            self._root.after(60_000, self._cerrar_pregunta)
        except Exception:  # pragma: no cover
            log.exception("no se pudo abrir la ventana de pregunta")

    def _responder(self, clave: str) -> None:
        try:
            self._respuestas.append(str(clave))
        finally:
            self._cerrar_pregunta()

    def _cerrar_pregunta(self) -> None:
        ventana = self._ventana_pregunta
        self._ventana_pregunta = None
        if ventana is not None:
            try:
                ventana.destroy()
            except Exception:  # pragma: no cover
                pass

    def _burbuja(self, texto: str) -> None:
        """Globo de texto sobre la cabeza, 4 s."""
        c = self._lienzo
        t = self._tema
        w = self._w
        c.delete("burbuja")
        ancho_texto = min(260, 12 + 7 * len(texto))
        x1 = max(2, int(w * 0.5) - ancho_texto // 2)
        x2 = min(int(w) - 2 + ancho_texto, x1 + ancho_texto)
        # la burbuja puede salir del lienzo: se dibuja dentro de lo posible
        x1 = 4
        x2 = max(60, min(int(w) - 4, ancho_texto + 10))
        c.create_rectangle(
            x1, 2, x2, 40, fill=t["placa"], outline=t["tinta"], width=2,
            tags=("burbuja",),
        )
        c.create_polygon(
            x1 + 18, 40, x1 + 30, 40, x1 + 22, 52,
            fill=t["placa"], outline=t["tinta"], width=2, tags=("burbuja",),
        )
        c.create_text(
            (x1 + x2) / 2, 21, text=texto[:34], fill=t["tinta"],
            font=("Segoe UI", 9), width=x2 - x1 - 12, tags=("burbuja",),
        )

        def _quitar() -> None:
            try:
                c.delete("burbuja")
            except Exception:  # pragma: no cover
                pass

        try:
            self._root.after(4000, _quitar)
        except Exception:  # pragma: no cover
            pass
