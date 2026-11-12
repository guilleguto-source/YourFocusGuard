"""Ventana flotante nativa transparente de Windows (v0.8.1).

Incluye:
- Menú contextual con clic derecho (Ajustes, 3 tamaños, cambio de mascota, cerrar).
- Modo TDAH Calmo (movimientos relajados, parpadeos suaves).
- Always-on-top y arrastrable libremente con el botón izquierdo.
"""
from __future__ import annotations

import json
import logging
import re
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path
from yourfocusguard.pet_sprite_player import SpriteSheetPlayer, TAMAÑOS_ESCALA

log = logging.getLogger(__name__)

COLOR_TRANSPARENTE = "#000001"
STATIC_DIR = Path(__file__).resolve().parent / "panel_static"


def _crear_rect_redondeado(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radio: int = 6, **kwargs) -> int:
    """Dibuja un rectángulo con esquinas redondeadas y suaves mediante Bezier en Tkinter."""
    puntos = [
        x1 + radio, y1,
        x1 + radio, y1,
        x2 - radio, y1,
        x2 - radio, y1,
        x2, y1,
        x2, y1 + radio,
        x2, y1 + radio,
        x2, y2 - radio,
        x2, y2 - radio,
        x2, y2,
        x2 - radio, y2,
        x2 - radio, y2,
        x1 + radio, y2,
        x1 + radio, y2,
        x1, y2,
        x1, y2 - radio,
        x1, y2 - radio,
        x1, y1 + radio,
        x1, y1 + radio,
        x1, y1,
    ]
    return canvas.create_polygon(puntos, smooth=True, **kwargs)


class MascotaFlotanteNativa:
    def __init__(self, mascota_id: str = "null-wisp", puerto: int = 8756, tamaño: str = "normal") -> None:
        self.puerto = puerto
        self.mascota_id = mascota_id
        self.tamaño = tamaño
        self.estado_actual = "idle"
        self.player: SpriteSheetPlayer | None = None
        self.frames: list[tk.PhotoImage] = []
        self.frame_idx = 0
        self.delay_ms = 500
        self._timer_resumen_id = None
        self._timer_countdown_id = None
        self._ultimo_texto_burbuja = ""
        self._ultimas_opciones: list[str] = []
        self._opciones_activas: list[str] = []
        self._countdown_seg = 0

        # Ventana Tkinter
        self.root = tk.Tk()
        self.root.title("YourFocusGuard Pet Native")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", COLOR_TRANSPARENTE)
        self.root.configure(bg=COLOR_TRANSPARENTE)

        # Dimensiones base según escala
        self._ajustar_dimensiones_ventana()

        # Canvas superior: Burbuja y controles
        self.canvas_burbuja = tk.Canvas(
            self.root, width=self.ancho_win, height=self.alto_burbuja, bg=COLOR_TRANSPARENTE, highlightthickness=0
        )
        self.canvas_burbuja.pack(side="top", fill="x")

        # Canvas inferior: Sprite de la mascota
        self.canvas_pet = tk.Canvas(
            self.root, width=self.ancho_win, height=self.alto_pet, bg=COLOR_TRANSPARENTE, highlightthickness=0
        )
        self.canvas_pet.pack(side="bottom", fill="both", expand=True)

        self.sprite_item = self.canvas_pet.create_image(self.ancho_win // 2, self.alto_pet // 2, image=None)

        # Eventos del ratón: clic izquierdo para arrastrar
        self._offset_x = 0
        self._offset_y = 0
        self.canvas_pet.bind("<Button-1>", self._iniciar_arrastre)
        self.canvas_pet.bind("<B1-Motion>", self._al_arrastrar)
        self.canvas_pet.bind("<Double-Button-1>", lambda e: self._hablar_con_mascota())

        # Clic derecho: Menú contextual
        self._crear_menu_contextual()
        self.canvas_pet.bind("<Button-3>", self._mostrar_menu)
        self.canvas_burbuja.bind("<Button-3>", self._mostrar_menu)

        # Atajo global de teclado para invocar micrófono
        self._iniciar_atajo_global()

        # Cargar sprite inicial
        self._cargar_mascota(self.mascota_id)

        # Animación y sondeo de backend
        self._animar()
        self._poll_backend()
        self._mostrar_burbuja("")

    def _ajustar_dimensiones_ventana(self) -> None:
        escala = TAMAÑOS_ESCALA.get(self.tamaño, 0.55)
        self.ancho_win = int(240 * (escala / 0.55))
        self.alto_pet = int(140 * (escala / 0.55))
        self.alto_burbuja = 74
        self.alto_win = self.alto_burbuja + self.alto_pet

        import ctypes, ctypes.wintypes
        rc = ctypes.wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)
        max_x = rc.right if rc.right > 0 else self.root.winfo_screenwidth()
        max_y = rc.bottom if rc.bottom > 0 else self.root.winfo_screenheight()

        x_init = max(0, max_x - self.ancho_win - 30)
        y_init = max(0, max_y - self.alto_win - 30)
        self.root.geometry(f"{self.ancho_win}x{self.alto_win}+{x_init}+{y_init}")

    def _crear_menu_contextual(self) -> None:
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="🎤 Hablar con la Mascota (Ctrl+Alt+M)", command=self._hablar_con_mascota)
        self.menu.add_command(label="🗣️ Saludo de Mascota (Probar Voz)", command=self._probar_voz)
        self.menu.add_command(label="⚙️ Ajustes del Guardián...", command=self._abrir_panel)
        self.menu.add_separator()

        # Submenú catálogo de 6 voces
        submenu_voces = tk.Menu(self.menu, tearoff=0)
        from yourfocusguard.actions.tts import PERFILES_VOZ, fijar_perfil_voz, reproducir_muestra
        for pid, meta in PERFILES_VOZ.items():
            def _elegir(p=pid):
                fijar_perfil_voz(p)
                reproducir_muestra(p)
                self._mostrar_burbuja(f"Voz: {PERFILES_VOZ[p]['nombre']}")
            submenu_voces.add_command(label=meta["nombre"], command=_elegir)
        self.menu.add_cascade(label="🗣️ Voces Disponibles", menu=submenu_voces)

        # Submenú tamaños
        submenu_tam = tk.Menu(self.menu, tearoff=0)
        submenu_tam.add_command(label="Pequeño", command=lambda: self._cambiar_tamaño("pequeño"))
        submenu_tam.add_command(label="Normal", command=lambda: self._cambiar_tamaño("normal"))
        submenu_tam.add_command(label="Grande", command=lambda: self._cambiar_tamaño("grande"))
        self.menu.add_cascade(label="📏 Tamaño", menu=submenu_tam)

        # Submenú mascotas completo (59 mascotas organizadas por iniciales)
        submenu_mascotas = tk.Menu(self.menu, tearoff=0)
        try:
            from yourfocusguard.panel import pet_listar_disponibles
            todas_mascotas = pet_listar_disponibles()
        except Exception:
            todas_mascotas = [{"id": "null-wisp", "nombre": "Null Wisp"}]

        grupos = {
            "A - C": [],
            "D - G": [],
            "H - M": [],
            "N - R": [],
            "S - Z": [],
        }
        for p in todas_mascotas:
            ini = (p.get("nombre") or p["id"])[0].upper()
            if ini in "ABC":
                grupos["A - C"].append(p)
            elif ini in "DEFG":
                grupos["D - G"].append(p)
            elif ini in "HIJKLM":
                grupos["H - M"].append(p)
            elif ini in "NOPQR":
                grupos["N - R"].append(p)
            else:
                grupos["S - Z"].append(p)

        for etiqueta, lista in grupos.items():
            if not lista:
                continue
            sub_grupo = tk.Menu(submenu_mascotas, tearoff=0)
            for pet in lista:
                sub_grupo.add_command(
                    label=pet["nombre"],
                    command=lambda pid=pet["id"]: self._seleccionar_mascota(pid),
                )
            submenu_mascotas.add_cascade(label=f"📁 {etiqueta} ({len(lista)})", menu=sub_grupo)

        self.menu.add_cascade(label=f"🐾 Cambiar Mascota ({len(todas_mascotas)})", menu=submenu_mascotas)

        self.menu.add_separator()
        self.menu.add_command(label="❌ Ocultar Mascota", command=self.root.destroy)

    def _mostrar_menu(self, event: tk.Event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _abrir_panel(self) -> None:
        webbrowser.open(f"http://127.0.0.1:{self.puerto}")

    def _probar_voz(self) -> None:
        try:
            from yourfocusguard.actions import tts
            tts.speak("¡Hola! Soy tu compañero de enfoque. ¡Vamos a tener una gran sesión!")
        except Exception as exc:
            log.warning("Error al probar voz: %s", exc)

    def _hablar_con_mascota(self) -> None:
        try:
            from yourfocusguard.actions.groq_voice import hablar_con_mascota_async
            # v0.8.3: el botón 🎤 respeta el modo privado del agente (0 micrófono,
            # 0 nube). Se consulta el estado en vivo del panel; si el panel no
            # responde, se procede porque el botón es una acción explícita del
            # usuario y sin agente en marcha no hay sesión que proteger.
            info = self._obtener_info_agente()
            if info.get("modo_privado"):
                self._mostrar_burbuja("🤫 Modo privado: sin voz por ahora.")
                log.info("Botón de voz ignorado: modo privado activo (0 micrófono, 0 nube).")
                return
            segundos = float(info.get("segundos_escucha", 8.0))
            self._mostrar_burbuja("🎤 Te escucho...")
            hablar_con_mascota_async(segundos=segundos)
        except Exception as exc:
            log.warning("Fallo al iniciar diálogo con mascota: %s", exc)

    def _obtener_info_agente(self) -> dict:
        """Consulta al panel local el estado del agente y configuración de voz (v0.8.3)."""
        try:
            url = f"http://127.0.0.1:{self.puerto}/api/estado"
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                datos = json.loads(resp.read().decode("utf-8"))
            estado = datos.get("estado") or {}
            cfg = datos.get("config") or {}
            return {
                "modo_privado": bool(estado.get("modo_privado", False)),
                "segundos_escucha": float(cfg.get("voz_segundos_escucha", 8.0)),
            }
        except Exception:
            return {"modo_privado": False, "segundos_escucha": 8.0}

    def _agente_en_modo_privado(self) -> bool:
        """Consulta al panel local si el agente está en modo privado (v0.8.3)."""
        return self._obtener_info_agente().get("modo_privado", False)

    def _cambiar_tamaño(self, nuevo_tam: str) -> None:
        if nuevo_tam != self.tamaño and self.player:
            self.tamaño = nuevo_tam
            self.player.cambiar_tamaño(nuevo_tam)
            self._ajustar_dimensiones_ventana()
            self.canvas_burbuja.config(width=self.ancho_win, height=self.alto_burbuja)
            self.canvas_pet.config(width=self.ancho_win, height=self.alto_pet)
            self.canvas_pet.coords(self.sprite_item, self.ancho_win // 2, self.alto_pet // 2)
            self._actualizar_frames()

    def _seleccionar_mascota(self, nuevo_id: str) -> None:
        self._cargar_mascota(nuevo_id)
        # Sincronizar con el panel web
        try:
            url = f"http://127.0.0.1:{self.puerto}/api/pet/set-pet"
            body = json.dumps({"mascota": nuevo_id}).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=0.5)
        except Exception:
            pass

    def _cargar_mascota(self, mascota_id: str) -> None:
        self.mascota_id = mascota_id
        d = STATIC_DIR / "pets" / mascota_id
        ruta_sprite = d / "spritesheet.webp"
        if not ruta_sprite.is_file():
            hallados = list(d.glob("**/spritesheet.webp"))
            if hallados:
                ruta_sprite = hallados[0]
        if ruta_sprite.is_file():
            self.player = SpriteSheetPlayer(
                ruta_sprite, tamaño=self.tamaño, color_clave=COLOR_TRANSPARENTE, modo_tdah=True
            )
            self._actualizar_frames()

    def _actualizar_frames(self) -> None:
        if self.player:
            self.frames, _ = self.player.obtener_frames(self.estado_actual)
            self.frame_idx = 0

    def _animar(self) -> None:
        if self.frames and self.player:
            self.frame_idx, self.delay_ms = self.player.siguiente_frame_index(
                self.estado_actual, self.frame_idx, len(self.frames)
            )
            self.canvas_pet.itemconfig(self.sprite_item, image=self.frames[self.frame_idx])
        self.root.after(self.delay_ms, self._animar)

    def _mostrar_burbuja(self, texto: str, opciones: list[str] | None = None, auto_confirmar_seg: int = 0, es_resumen: bool = False) -> None:
        self.canvas_burbuja.delete("all")
        if not es_resumen:
            self._ultimo_texto_burbuja = texto
            if self._timer_resumen_id:
                self.root.after_cancel(self._timer_resumen_id)
                self._timer_resumen_id = None
        if self._timer_countdown_id:
            self.root.after_cancel(self._timer_countdown_id)
            self._timer_countdown_id = None

        self._opciones_activas = list(opciones or [])
        w = max(195, self.ancho_win - 10)
        h_bubble = 0

        # 1. Caja de texto / aviso superior autoajustable
        if texto:
            t_item = self.canvas_burbuja.create_text(
                (w + 10) // 2, 0,
                text=texto, width=w - 18, font=("Segoe UI", 8, "bold"), fill="#27241E", justify="center"
            )
            bbox = self.canvas_burbuja.bbox(t_item)
            text_h = (bbox[3] - bbox[1]) if bbox else 26
            h_bubble = max(34, text_h + 16)

            self.canvas_burbuja.coords(t_item, (w + 10) // 2, 2 + h_bubble // 2)

            bg_bubble = _crear_rect_redondeado(
                self.canvas_burbuja, 4, 2, w + 6, h_bubble, radio=10,
                fill="#FFFFFF", outline="#D3CCBE", width=1.5
            )
            self.canvas_burbuja.tag_lower(bg_bubble, t_item)

            cola = self.canvas_burbuja.create_polygon(
                (w + 10) // 2 - 5, h_bubble - 1,
                (w + 10) // 2 + 5, h_bubble - 1,
                (w + 10) // 2, h_bubble + 5,
                fill="#FFFFFF", outline="#D3CCBE"
            )
            self.canvas_burbuja.tag_lower(cola, t_item)

            # Si es texto largo sin opciones, activar temporizador de 30 segundos
            if not es_resumen and not self._opciones_activas and (len(texto) > 60 or "\n" in texto):
                self._timer_resumen_id = self.root.after(30000, lambda: self._mostrar_resumen(texto))

        # 2. Fila de botones (opciones interactivas o botones estándar)
        by0 = (h_bubble + 9) if texto else 4
        by1 = by0 + 22

        def _crear_boton(tag, x0, x1, texto_btn, icono, color_texto, bg_normal, border_normal, bg_hover, border_hover, accion):
            _crear_rect_redondeado(
                self.canvas_burbuja, x0, by0, x1, by1, radio=8,
                fill=bg_normal, outline=border_normal, width=1.2, tags=(tag, f"{tag}_bg")
            )
            self.canvas_burbuja.create_text(
                (x0 + x1) // 2, (by0 + by1) // 2,
                text=f"{icono} {texto_btn}" if icono else texto_btn,
                font=("Segoe UI", 7, "bold"), fill=color_texto, tags=(tag, f"{tag}_txt")
            )
            self.canvas_burbuja.tag_bind(tag, "<Button-1>", lambda e: accion())
            self.canvas_burbuja.tag_bind(tag, "<Enter>", lambda e: (
                self.canvas_burbuja.itemconfig(f"{tag}_bg", fill=bg_hover, outline=border_hover),
                self.root.config(cursor="hand2")
            ))
            self.canvas_burbuja.tag_bind(tag, "<Leave>", lambda e: (
                self.canvas_burbuja.itemconfig(f"{tag}_bg", fill=bg_normal, outline=border_normal),
                self.root.config(cursor="")
            ))

        if self._opciones_activas and len(self._opciones_activas) >= 2:
            # Modo Confirmación con 2 botones píldora (ej: Agendar / Cancelar)
            btn_w = (self.ancho_win - 20) // 2
            bx0 = 6
            bx1 = bx0 + btn_w
            cx0 = bx1 + 8
            cx1 = self.ancho_win - 6

            self._countdown_seg = auto_confirmar_seg if auto_confirmar_seg > 0 else 0
            txt_opc0 = f"{self._opciones_activas[0]} ({self._countdown_seg}s)" if self._countdown_seg > 0 else self._opciones_activas[0]

            _crear_boton(
                "btn_opc0", bx0, bx1, txt_opc0, "✅", "#4D6B53",
                "#FDFBF7", "#5C6E52", "#E9EFE7", "#4D6B53",
                lambda: self._ejecutar_respuesta_opcion(self._opciones_activas[0])
            )
            _crear_boton(
                "btn_opc1", cx0, cx1, self._opciones_activas[1], "❌", "#B45309",
                "#FDFBF7", "#D8D2C4", "#F5EFE6", "#B45309",
                lambda: self._ejecutar_respuesta_opcion(self._opciones_activas[1])
            )

            if self._countdown_seg > 0:
                self._timer_countdown_id = self.root.after(1000, self._tick_countdown)

        else:
            # Modo Estándar de 3 botones
            btn_w = (self.ancho_win - 26) // 3
            bx0 = 5
            bx1 = bx0 + btn_w
            _crear_boton(
                "btn_pause10", bx0, bx1, "10m", "⏸", "#B45309",
                "#FDFBF7", "#D8D2C4", "#F5EFE6", "#B45309",
                lambda: self._enviar_control({"cmd": "pause_manual", "minutos": 10, "espera_confirmacion": True})
            )
            cx0 = bx1 + 6
            cx1 = cx0 + btn_w
            _crear_boton(
                "btn_hablar", cx0, cx1, "Hablar", "🎤", "#2F2B25",
                "#F5F3EF", "#D1CABE", "#EAE5DC", "#5D584C",
                lambda: self._hablar_con_mascota()
            )
            dx0 = cx1 + 6
            dx1 = self.ancho_win - 5
            _crear_boton(
                "btn_cont15", dx0, dx1, "+15m", "▶", "#4D6B53",
                "#FDFBF7", "#D8D2C4", "#E9EFE7", "#4D6B53",
                lambda: self._enviar_control({"cmd": "resume_or_extend", "minutos": 15})
            )

        # 3. Ajuste dinámico de ventana según el tamaño del contenido
        nuevo_alto_burbuja = by1 + 6
        if self.alto_burbuja != nuevo_alto_burbuja:
            self.alto_burbuja = nuevo_alto_burbuja
            self.alto_win = self.alto_burbuja + self.alto_pet
            cur_x = self.root.winfo_x()
            cur_y = self.root.winfo_y()
            self.root.geometry(f"{self.ancho_win}x{self.alto_win}+{cur_x}+{cur_y}")
            self.canvas_burbuja.config(height=self.alto_burbuja)

    def _tick_countdown(self) -> None:
        """Actualiza la cuenta regresiva de 15s en el botón de confirmación."""
        if self._countdown_seg > 1:
            self._countdown_seg -= 1
            if self._opciones_activas:
                self.canvas_burbuja.itemconfig("btn_opc0_txt", text=f"✅ {self._opciones_activas[0]} ({self._countdown_seg}s)")
            self._timer_countdown_id = self.root.after(1000, self._tick_countdown)
        else:
            self._countdown_seg = 0
            if self._opciones_activas:
                self._ejecutar_respuesta_opcion(self._opciones_activas[0])

    def _ejecutar_respuesta_opcion(self, opcion: str) -> None:
        """Ejecuta la opción seleccionada (manual o por cuenta regresiva)."""
        if self._timer_countdown_id:
            self.root.after_cancel(self._timer_countdown_id)
            self._timer_countdown_id = None
        opciones_previas = list(self._opciones_activas)
        self._opciones_activas = []

        def _post():
            try:
                url = f"http://127.0.0.1:{self.puerto}/api/pet/responder"
                data = json.dumps({"respuesta": opcion}).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json", "User-Agent": "YFG-PetNative"}
                )
                with urllib.request.urlopen(req, timeout=1.0):
                    pass
            except Exception as e:
                log.debug("Error respondiendo opción: %s", e)

        import threading
        threading.Thread(target=_post, daemon=True).start()

        if "cancel" in opcion.lower():
            self._mostrar_burbuja("Cancelado. No agendé nada.")
        else:
            self._mostrar_burbuja("¡Listo! Agendado con éxito.")

    def _mostrar_resumen(self, texto_original: str) -> None:
        """Contrae el mensaje largo a un resumen conciso tras 30s."""
        self._timer_resumen_id = None
        partes = [p.strip() for p in re.split(r"[.¿?¡!\n]", texto_original) if len(p.strip()) > 3]
        if partes and len(partes[0]) <= 45:
            resumen = partes[0] + "…"
        else:
            resumen = texto_original[:38].strip() + "…"
        self._mostrar_burbuja(resumen, es_resumen=True)

    def _enviar_control(self, payload: dict) -> None:
        def _post():
            try:
                url = f"http://127.0.0.1:{self.puerto}/api/control"
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data,
                    headers={"Content-Type": "application/json", "User-Agent": "YFG-PetNative"}
                )
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    pass
            except Exception as e:
                log.debug("Error enviando control desde pet nativo: %s", e)

        import threading
        threading.Thread(target=_post, daemon=True).start()

    def _iniciar_atajo_global(self) -> None:
        def _escuchar_atajo():
            try:
                import keyboard
                keyboard.add_hotkey("ctrl+alt+m", lambda: self.root.after(0, self._hablar_con_mascota))
            except Exception as exc:
                log.debug("Atajo global no registrado: %s", exc)

        import threading
        t = threading.Thread(target=_escuchar_atajo, name="hotkey-voice", daemon=True)
        t.start()

    def _poll_backend(self) -> None:
        try:
            url = f"http://127.0.0.1:{self.puerto}/api/pet/state"
            req = urllib.request.Request(url, headers={"User-Agent": "YFG-PetNative"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                nueva_mascota = data.get("mascota")
                if nueva_mascota and nueva_mascota != self.mascota_id:
                    self._cargar_mascota(nueva_mascota)

                nueva_reaccion = data.get("reaccion") or "idle"
                if nueva_reaccion != self.estado_actual:
                    self.estado_actual = nueva_reaccion
                    self._actualizar_frames()

                burbuja = data.get("burbuja", {})
                txt_burbuja = burbuja.get("texto", "")
                opciones = burbuja.get("opciones", [])
                auto_seg = burbuja.get("auto_confirmar_seg", 0)
                if txt_burbuja != self._ultimo_texto_burbuja or opciones != self._ultimas_opciones:
                    self._ultimas_opciones = list(opciones)
                    self._mostrar_burbuja(txt_burbuja, opciones=opciones, auto_confirmar_seg=auto_seg)
        except Exception:
            pass
        finally:
            self.root.after(800, self._poll_backend)

    def _iniciar_arrastre(self, event: tk.Event) -> None:
        self._offset_x = event.x
        self._offset_y = event.y

    def _al_arrastrar(self, event: tk.Event) -> None:
        x = self.root.winfo_x() + (event.x - self._offset_x)
        y = self.root.winfo_y() + (event.y - self._offset_y)
        self.root.geometry(f"+{x}+{y}")

    def iniciar(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    import sys
    mascota = sys.argv[1] if len(sys.argv) > 1 else "null-wisp"
    puerto = int(sys.argv[2]) if len(sys.argv) > 2 else 8756
    tamaño = sys.argv[3] if len(sys.argv) > 3 else "normal"
    app = MascotaFlotanteNativa(mascota_id=mascota, puerto=puerto, tamaño=tamaño)
    app.iniciar()
