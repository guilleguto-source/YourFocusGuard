"""Limpieza de residuos del proyecto (v0.10).

Borra del proyecto los archivos que ya nadie usa y solo confunden:

- `docker-compose.yml` / `Dockerfile` / `.dockerignore` / `redis-data/`:
  el asistente es nativo de Windows (winsound, OAuth con navegador), nunca
  corrió en Docker, y el compose declaraba un Redis que nadie consume.
- `app/stt.py`: el STT lo hace el navegador (SpeechRecognition API),
  el módulo no se importa desde v0.9.
- `app/music.py`: stub de Spotify abandonado.
- `app/config.py`: config leída directamente de config.json + .env.

Uso (desde la raíz del proyecto):
    python limpiar_residuos.py --solo-ver   # solo muestra qué borraría
    python limpiar_residuos.py              # borra de verdad (pide confirmar)
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

OBSOLETOS = [
    "docker-compose.yml",
    "Dockerfile",
    ".dockerignore",
    "redis-data",
    "app/stt.py",
    "app/music.py",
    "app/config.py",
]

#: Imports que NO deben existir en el código actual (si existen, no borrar)
IMPORTS_PROHIBIDOS = {
    "app/stt.py": ("from stt import", "import stt"),
    "app/music.py": ("from music import", "import music"),
    "app/config.py": ("from config import", "import config"),
}


def hay_imports_activos(ruta_relativa: str) -> bool:
    """True si algún otro archivo .py aún importa el módulo obsoleto."""
    patrones = IMPORTS_PROHIBIDOS.get(ruta_relativa, ())
    for py in RAIZ.rglob("*.py"):
        rel = str(py.relative_to(RAIZ)).replace("\\", "/")
        if rel == ruta_relativa:
            continue
        try:
            contenido = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for patron in patrones:
            # "import config" NO debe matchear "import configdot"... ajuste simple
            for linea in contenido.splitlines():
                limpia = linea.strip()
                if limpia.startswith("#"):
                    continue
                if limpia.startswith(patron):
                    print(f"  ⚠️  {rel} todavía usa: '{limpia}'")
                    return True
    return False


def main() -> int:
    solo_ver = "--solo-ver" in sys.argv

    print("\n=== Limpieza de residuos (v0.10) ===\n")

    if solo_ver:
        print("MODO SOLO-VER: nada se borra, solo se muestra.\n")

    a_borrar = []
    for rel in OBSOLETOS:
        ruta = RAIZ / rel
        if not ruta.exists():
            continue
        if rel in IMPORTS_PROHIBIDOS and hay_imports_activos(rel):
            print(f"  ✋ NO se borrará {rel}: otro archivo aún lo importa.")
            continue
        a_borrar.append((ruta, rel))

    if not a_borrar:
        print("Nada que limpiar. Tu proyecto ya está libre de residuos. ✨\n")
        return 0

    for ruta, rel in a_borrar:
        tipo = "carpeta" if ruta.is_dir() else "archivo"
        print(f"  🗑  {rel} ({tipo})")

    if solo_ver:
        print(f"\nSe limpiarían {len(a_borrar)} elemento(s).")
        print("Ejecuta sin --solo-ver para borrarlos de verdad.")
        return 0

    resp = input(f"\n¿Borrar {len(a_borrar)} elemento(s)? [s/N]: ").strip().lower()
    if resp not in ("s", "si", "sí"):
        print("Cancelado. No se borró nada.")
        return 0

    borrados = 0
    for ruta, rel in a_borrar:
        try:
            if ruta.is_dir():
                shutil.rmtree(ruta)
            else:
                ruta.unlink()
            borrados += 1
            print(f"  ✅ Borrado: {rel}")
        except Exception as e:
            print(f"  ❌ No se pudo borrar {rel}: {e}")

    print(f"\nListo: {borrados}/{len(a_borrar)} eliminados.")
    print("Tu proyecto quedó más liviano y sin código muerto. ✨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
