"""Escritor atómico y seguro para user.toml sin corromper configuraciones existentes."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def agregar_app_relacionada_en_toml(
    ruta_user_toml: Path,
    grupo_nombre: str,
    nueva_app: str,
) -> bool:
    """Añade de forma segura una app relacionada a un grupo de flujo en user.toml."""
    ruta = Path(ruta_user_toml)
    if not ruta.is_file():
        # Crear estructura básica si no existe
        contenido = (
            f"[[flujos.grupo]]\n"
            f'nombre = "{grupo_nombre}"\n'
            f'apps = []\n'
            f'apps_relacionadas = ["{nueva_app.lower()}"]\n'
        )
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
        return True

    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        log.error("No se pudo leer %s: %s", ruta, exc)
        return False

    nueva_app_norm = nueva_app.strip().lower()

    # Buscar bloque [[flujos.grupo]] con el nombre
    lineas = texto.splitlines()
    en_grupo_deseado = False
    indice_insertar = None
    app_ya_existe = False

    for idx, linea in enumerate(lineas):
        l_strip = linea.strip()
        if l_strip.startswith("[[flujos.grupo]]"):
            en_grupo_deseado = False
        elif en_grupo_deseado and "apps_relacionadas" in l_strip:
            if nueva_app_norm in l_strip.lower():
                app_ya_existe = True
                return True
            # Agregar la app a la lista existente
            partes = linea.split("=", 1)
            if len(partes) == 2:
                lista_str = partes[1].strip()
                if lista_str.endswith("]"):
                    items_existentes = [x.strip().strip('"\'') for x in lista_str.strip("[]").split(",") if x.strip()]
                    if nueva_app_norm not in items_existentes:
                        items_existentes.append(nueva_app_norm)
                    nuevo_valor = "[" + ", ".join(f'"{x}"' for x in items_existentes) + "]"
                    lineas[idx] = f"{partes[0]}= {nuevo_valor}"
                    _guardar_atomico(ruta, "\n".join(lineas) + "\n")
                    return True
        elif f'nombre = "{grupo_nombre}"' in l_strip or f"nombre = '{grupo_nombre}'" in l_strip:
            en_grupo_deseado = True
            indice_insertar = idx

    if app_ya_existe:
        return True

    # Si el grupo existía pero no tenía apps_relacionadas
    if en_grupo_deseado and indice_insertar is not None:
        lineas.insert(indice_insertar + 1, f'apps_relacionadas = ["{nueva_app_norm}"]')
        _guardar_atomico(ruta, "\n".join(lineas) + "\n")
        return True

    # Si no existía el grupo, agregarlo al final
    nuevo_bloque = (
        f"\n[[flujos.grupo]]\n"
        f'nombre = "{grupo_nombre}"\n'
        f'apps_relacionadas = ["{nueva_app_norm}"]\n'
    )
    _guardar_atomico(ruta, texto.rstrip() + "\n" + nuevo_bloque)
    return True


def _guardar_atomico(ruta: Path, contenido: str) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(contenido, encoding="utf-8")
    tmp.replace(ruta)
