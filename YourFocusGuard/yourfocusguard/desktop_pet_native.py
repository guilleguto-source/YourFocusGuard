"""Ventana flotante nativa transparente de Windows (v0.8.1).

Incluye:
- Menú contextual con clic derecho (Ajustes, 3 tamaños, cambio de mascota, cerrar).
- Modo TDAH Calmo (movimientos relajados, parpadeos suaves).
- Always-on-top y arrastrable libremente con el botón izquierdo.
"""
from __future__ import annotations

import json
import logging
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path
from yourfocusguard.pet_sprite_player import SpriteSheetPlayer, TAMAÑOS_ESCALA

log = logging.getLogger(__name__)

COLOR_TRANSPARENTE = "#000001"
STATIC_DIR = Path(__file__).resolve().parent / "panel_static"


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

    def _mostrar_burbuja(self, texto: str) -> None:
        self.canvas_burbuja.delete("all")
        w = max(180, self.ancho_win - 8)

        # 1. Caja de texto / aviso superior
        if texto:
            h_bubble = 48
            self.canvas_burbuja.create_rectangle(4, 2, w + 4, h_bubble, fill="#FFFFFF", outline="#D8D2C4", width=1.5)
            self.canvas_burbuja.create_polygon(
                (w + 8) // 2 - 4, h_bubble,
                (w + 8) // 2 + 4, h_bubble,
                (w + 8) // 2, h_bubble + 3,
                fill="#FFFFFF", outline="#D8D2C4"
            )
            self.canvas_burbuja.create_text(
                (w + 8) // 2, h_bubble // 2 + 1,
                text=texto, width=w - 12, font=("Segoe UI", 6, "bold"), fill="#2F2B25"
            )

        # 2. Fila fija de botones en la parte inferior (siempre visible)
        by0 = 52
        by1 = 72
        btn_w = (self.ancho_win - 28) // 3

        # Botón 1: Pausar 10m
        bx0 = 6
        bx1 = bx0 + btn_w
        self.canvas_burbuja.create_rectangle(bx0, by0, bx1, by1, fill="#FDFBF7", outline="#D8D2C4", width=1, tags="btn_pause10")
        self.canvas_burbuja.create_text((bx0 + bx1) // 2, (by0 + by1) // 2, text="⏸ 10m", font=("Segoe UI", 7, "bold"), fill="#B45309", tags="btn_pause10")
        self.canvas_burbuja.tag_bind("btn_pause10", "<Button-1>", lambda e: self._enviar_control({"cmd": "pause_manual", "minutos": 10, "espera_confirmacion": True}))

        # Botón 2: Hablar
        cx0 = bx1 + 8
        cx1 = cx0 + btn_w
        self.canvas_burbuja.create_rectangle(cx0, by0, cx1, by1, fill="#F5F3EF", outline="#D1CABE", width=1.2, tags="btn_hablar")
        self.canvas_burbuja.create_text((cx0 + cx1) // 2, (by0 + by1) // 2, text="🎤 Hablar", font=("Segoe UI", 7, "bold"), fill="#4A443A", tags="btn_hablar")
        self.canvas_burbuja.tag_bind("btn_hablar", "<Button-1>", lambda e: self._hablar_con_mascota())

        # Botón 3: Continuar +15m
        dx0 = cx1 + 8
        dx1 = self.ancho_win - 6
        self.canvas_burbuja.create_rectangle(dx0, by0, dx1, by1, fill="#FDFBF7", outline="#D8D2C4", width=1, tags="btn_cont15")
        self.canvas_burbuja.create_text((dx0 + dx1) // 2, (by0 + by1) // 2, text="▶ +15m", font=("Segoe UI", 7, "bold"), fill="#5C6E52", tags="btn_cont15")
        self.canvas_burbuja.tag_bind("btn_cont15", "<Button-1>", lambda e: self._enviar_control({"cmd": "resume_or_extend", "minutos": 15}))

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
                self._mostrar_burbuja(burbuja.get("texto", ""))
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
