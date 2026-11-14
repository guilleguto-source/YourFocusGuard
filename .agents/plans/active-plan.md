# Plan: Corrección de Detección de Inactividad y Cronómetro de Foco Real

## Diagnóstico Raíz
1. **Scheduler Ciego al Tiempo Real (`scheduler.py`)**: `verificar_pendientes()` calculaba la pausa activa mediante tiempo absoluto de reloj (`ahora - _ultimo_check_rutina >= 50m`), sin importar si el usuario estaba ausente o en pausa.
2. **Ubicación en Tick del Motor (`engine.py`)**: `_verificar_scheduler(ahora)` se ejecutaba al inicio de cada ciclo antes de evaluar pausas, ausencias o inactividad del teclado/ratón.
3. **Acumulación Falsa en Guardián (`session_guard.py`)**: `seg_en_app` acumulaba segundos continuamente siempre que la ventana activa fuera de trabajo (`!= FUERA`), ignorando si `idle_seg >= segundos_inactivo`.

## Archivos Afectados
- `YourFocusGuard/yourfocusguard/core/scheduler.py`
- `YourFocusGuard/yourfocusguard/session_guard.py`
- `YourFocusGuard/yourfocusguard/engine.py`
- `YourFocusGuard/tests/test_scheduler.py`
- `YourFocusGuard/tests/test_session_guard.py`

## Checklist de Implementación
- [ ] **1. `scheduler.py`**: Cambiar el timer de pausa activa de reloj absoluto a acumulación de tiempo de foco activo (`tiempo_foco_acumulado += delta_seg`). Si no hay foco activo (inactivo/pausa/ausencia), no acumula.
- [ ] **2. `session_guard.py`**: Condicionar el incremento de `seg_en_app` a que el usuario NO supere `segundos_inactivo` (90s). Si está congelado/idle, no suma tiempo de trabajo.
- [ ] **3. `engine.py`**: Pasar al scheduler el estado de foco activo (`en_foco = not en_pausa and not en_ausencia and idle < umbral`) y mover/condicionar el aviso a momentos de foco genuino.
- [ ] **4. Tests Unitarios**: Crear pruebas que verifiquen que tras 1 hora de idle/ausencia NO se dispara la pausa activa ni se infla `seg_en_app`.
- [ ] **5. Reinicio de Servicios**: Reiniciar los procesos en segundo plano con `detener_silencioso.vbs` e `iniciar_silencioso.vbs`.
