# Plan: Empaquetado Ligero para Auditoría y Manifiesto de Arquitectura

## Contexto
El usuario requiere un archivo ZIP optimizado para auditoría de código del Asistente TDAH / YourFocusGuard, junto con un documento explicativo que detalle la función de la suite y especifique exhaustivamente qué elementos se excluyeron para reducir el peso de ~800 MB a < 5 MB.

## Archivos a Generar
- `auditoria_asistente_tdah.zip` (en la raíz del workspace)
- `EXPLICACION_SISTEMA_Y_AUDITORIA.md` (incluido en el ZIP y en la raíz)

## Elementos Incluidos en el ZIP
- `adhd-assistant/` (código fuente completo, tests, APIs, herramientas, routers, prompts)
- `YourFocusGuard/` (código fuente completo, motor `engine.py`, `scheduler.py`, interfaz nativa PySide6, web dashboard, tests)
- `YourFocusGuard/config/` (configuraciones TOML base y de usuario)
- Scripts de control (`iniciar_silencioso.vbs`, `detener_silencioso.vbs`, bat launchers)
- Mascota activa (`einstein/` en `panel_static/pets/einstein`) para verificar la integración gráfica sin inflar peso.

## Elementos Excluidos del ZIP (Detallados en el Manifiesto)
1. `rea-analysis/` (~643.5 MB): Artefactos binarios de desensamblado y sesiones de ingeniería inversa.
2. `panel_static/pets/` (~93 MB de sprites secundarios): Se conservan únicamente los recursos de la mascota activa (*Einstein*); se excluyen las 58 mascotas alternas (Goku, Nezuko, etc.).
3. `data/fotos/` e imágenes temporales de webcam (~4 MB): Fotos de verificación de presencia.
4. `_pytmp/`, `.pytest_cache/`, `__pycache__/` (~3 MB): Caché de compilación bytecode y casos temporales de pytest.
5. `.git/`: Historial de commits y packfiles binarios de control de versiones.

## Checklist de Ejecución
- [ ] 1. Redactar `EXPLICACION_SISTEMA_Y_AUDITORIA.md` cubriendo descripción del programa, arquitectura dual, flujos y detalle de exclusiones.
- [ ] 2. Generar script empaquetador en PowerShell que comprima respetando exclusiones.
- [ ] 3. Validar integridad y tamaño del ZIP generado (< 5 MB).
- [ ] 4. Confirmar que el archivo explicativo quede accesible.
