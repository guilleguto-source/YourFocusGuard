"""Privacidad: lista de exclusiones (blueprint, cap. 7).

Las apps y títulos de la lista ni se capturan ni se evalúan: cuando la
ventana en primer plano coincide, el agente entra en pausa "privado", no
toca la pantalla y solo queda constancia del patrón que lo activó.
"""
from __future__ import annotations

import re


class Exclusiones:
    def __init__(self, apps: list[str], titulos: list[str]) -> None:
        self.apps = [a.strip().lower() for a in apps if a.strip()]
        self.titulos = [t.strip() for t in titulos if t.strip()]

    def excluida(self, app: str | None, titulo: str | None) -> str | None:
        """Patrón que disparó la exclusión, o None si la ventana no está excluida."""
        app_l = (app or "").strip().lower()
        for patron in self.apps:
            if patron in app_l:
                return f"app:{patron}"

        titulo_txt = titulo or ""
        for patron in self.titulos:
            try:
                if re.search(patron, titulo_txt, re.IGNORECASE):
                    return f"titulo:{patron}"
            except re.error:
                if patron.lower() in titulo_txt.lower():
                    return f"titulo:{patron}"
        return None

    def __bool__(self) -> bool:  # ¿hay alguna regla configurada?
        return bool(self.apps or self.titulos)
