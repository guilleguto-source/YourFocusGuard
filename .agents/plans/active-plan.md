# Plan: Aplicación de Endurecimiento v0.12.1 y Aislamiento del Widget Móvil

## Contexto
El usuario requiere aplicar todas las correcciones de estabilidad y seguridad de la auditoría (v0.12.1) al sistema principal, manteniendo la integración del celular / widget (proveniente de `1e73d4dd-031d-4224-bc5a-58c5d57b580c` / PhoneBox) de manera aislada y modular para probarlo por separado sin comprometer el funcionamiento actual.

## Estrategia de Segregación
1. **Fase 1: Núcleo y Endurecimiento (Producción Estable)**:
   - Aplicar correcciones de hosts y volumen exacto en `YourFocusGuard/yourfocusguard/actions/concentracion.py`.
   - Aplicar límites de seguridad en `adhd-assistant` (body 64KB, anti DNS-rebinding, "anota que..." incondicional, validación tipada, cancelación de alarmas en `timer.py`).
   - Servidor por defecto estrictamente atado a `127.0.0.1` (localhost puro).
2. **Fase 2: Aislamiento del Widget / Celular (Módulo Separado)**:
   - Los archivos de interfaz móvil (`widget.html`, `widget.js`, `widget.css`) se integran como endpoint pasivo `/widget` (sin exponer puertos ni alterar el panel web principal).
   - Crear script aislado `probar_widget_celular.bat` (o subcomando) para probar el enlace con el Nubia (sea por USB `adb reverse` o red) de forma controlada sin tocar la configuración de inicio silencioso del sistema principal.

## Archivos Afectados
- `YourFocusGuard/yourfocusguard/actions/concentracion.py` (hosts block + journal + volume DWORD)
- `YourFocusGuard/tests/test_concentracion_v085.py` (pruebas regresión guardián)
- `YourFocusGuard/requirements-lock.txt` y `CHANGELOG.md`
- `adhd-assistant/app/server.py` (endurecimiento HTTP + endpoint pasivo widget)
- `adhd-assistant/app/router.py` (captura directa de notas)
- `adhd-assistant/app/timer.py` (cancelación de alarmas)
- `adhd-assistant/app/ui/widget.*` (archivos estáticos aislados del celular)
- `adhd-assistant/pruebas_automaticas.py` (suite ampliada a 120 pruebas)
- `adhd-assistant/requirements-lock.txt`
- `probar_widget_celular.bat` (lanzador independiente para testing de móvil)

## Checklist de Ejecución
- [ ] 1. Descomprimir e integrar cambios de endurecimiento de `asistente_v0121_endurecimiento_widget.zip` sobre el código fuente.
- [ ] 2. Garantizar que el modo por defecto de `server.py` opere estrictamente en localhost sin exigir token a clientes locales.
- [ ] 3. Crear script de prueba dedicado `probar_widget_celular.bat` para verificar el Nubia Z17 Lite sin alterar los lanzadores silenciosos.
- [ ] 4. Ejecutar suites de verificación: `pytest YourFocusGuard/tests` (293 tests) y `python adhd-assistant/pruebas_automaticas.py` (120 tests).
- [ ] 5. Confirmar estado limpio en Git y documentar procedimiento de prueba aislada.
