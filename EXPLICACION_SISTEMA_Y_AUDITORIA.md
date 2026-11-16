# Dossier de Arquitectura y Auditoría: Asistente TDAH & YourFocusGuard

Este documento acompaña al paquete de código `auditoria_asistente_tdah.zip` para proporcionar a los auditores y desarrolladores una visión integral de la arquitectura, componentes, flujos de ejecución y el detalle exhaustivo de los recursos que fueron deliberadamente excluidos del archivo comprimido para optimizar su tamaño de transferencia e inspección.

---

## 1. ¿Qué es este programa?

Es una **suite de asistencia ejecutiva y soporte para personas con TDAH (Trastorno por Déficit de Atención e Hiperactividad)**. Está diseñada para mitigar problemas comunes de función ejecutiva: "ceguera temporal", disfunción de inicio de tareas, desvíos hiperfocados en aplicaciones no laborales y olvido de descansos físicos.

El sistema opera bajo una **arquitectura híbrida local y desacoplada** compuesta por dos servicios cooperativos y una mascota reactiva de escritorio:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ENTORNO LOCAL DEL USUARIO                       │
│                                                                        │
│   ┌────────────────────────┐             ┌─────────────────────────┐   │
│   │     adhd-assistant     │ ◄──HTTP───► │      YourFocusGuard     │   │
│   │   (Backend REST:8765)  │             │   (Motor Guardián:8756) │   │
│   │                        │             │                         │   │
│   │ • API FastAPI / SQLite │             │ • Detección Win32 (app/ │   │
│   │ • Vikunja / Google Cal │             │   título/idle/pantalla) │   │
│   │ • Router LLM (Groq)    │             │ • Escalera de alertas   │   │
│   │ • TTS neuronal local   │             │ • Scheduler foco real   │   │
│   │ • Gestión temporizador │             │ • Web Dashboard local   │   │
│   └────────────────────────┘             └────────────┬────────────┘   │
│                                                       │ Eventos IPC    │
│                                                       ▼                │
│                                          ┌─────────────────────────┐   │
│                                          │   desktop_pet_native    │   │
│                                          │ (Mascota Desktop PySide)│   │
│                                          │                         │   │
│                                          │ • Avatar animado        │   │
│                                          │ • Globos contextuales   │   │
│                                          │ • Micrófono Groq Voice  │   │
│                                          │ • Botones +5m / Pausa   │   │
│                                          └─────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Componentes del Sistema

### A. `adhd-assistant` (Servidor de Contexto, Memoria y Agenda)
- **Puerto:** `8765`
- **Tecnología:** Python 3.12, FastAPI / HTTP nativo, SQLite.
- **Responsabilidades:**
  - **Agenda y Tareas:** Sincronización bidireccional con Vikunja y Google Calendar.
  - **Memoria a Corto y Largo Plazo:** Almacenamiento indexado de notas, contexto de trabajo y preferencias.
  - **Enrutamiento Inteligente:** Clasificador semántico rápido (reglas regex + LLM Groq `llama-3.3-70b-versatile`) para atender peticiones por voz o texto.
  - **Motor de Audio/TTS:** Generación de voz neuronal en español (Edge-TTS / pyttsx3) y síntesis de ruido marrón/blanco para estimulación cognitiva.
  - **Suite de Pruebas:** `pruebas_automaticas.py` (101 pruebas de integración end-to-end).

### B. `YourFocusGuard` (Motor de Atención y Centinela de Aplicaciones)
- **Puerto:** `8756` (panel local)
- **Tecnología:** Python 3.12, Windows Win32 API (`pywin32`), PySide6 / Qt.
- **Responsabilidades:**
  - **Vigilancia No Intrusiva (`engine.py`, `session_guard.py`):** Monitorea la ventana en primer plano y el estado de inactividad de teclado/ratón (`GetLastInputInfo`) contra una lista de aplicaciones declaradas de trabajo (ej. Lightroom, Photoshop).
  - **Escalera de Desvío Progresiva (`escalation.py`):** Si el usuario se dispersa a redes sociales o navegadores, no castiga de golpe; ejecuta una escalera gentil (nivel 1 sutil, nivel 2 sugerencia hablada, nivel 3 traer la app de trabajo al frente tras N minutos).
  - **Scheduler de Foco Real (`scheduler.py`):** Recordatorios puntuales y rutinas de pausa activa ("50 minutos concentrado"). **Congela el tiempo** si el usuario se levanta o deja de tocar el teclado, evitando felicitaciones falsas o alarmas a destiempo.
  - **Suite de Pruebas:** `YourFocusGuard/tests/` (285 pruebas unitarias con `pytest`).

### C. Mascota de Escritorio (`desktop_pet_native.py`)
- **Tecnología:** PySide6 (Qt) con ventana transparente sin bordes y `WA_TranslucentBackground`.
- **Comportamiento:** Flota sobre el escritorio o sobre la ventana de trabajo. Se comunica mediante globos de diálogo estilo cómic con botones táctiles/accesibles (`[ ⏸ +5m ]`, `[ 🎤 ]`, `[ ▶ +5m ]`, `[ Sigo aquí ]`). Permite entrada rápida de comandos de voz mediante Groq Audio.

---

## 3. Guía de Ejecución y Auditoría

### Requisitos Previos
- Windows 10/11
- Python 3.11 o 3.12
- Dependencias base instaladas (`pip install -r YourFocusGuard/requirements.txt` y dependencias de `adhd-assistant`)

### Lanzamiento Silencioso (Producción)
- **Iniciar:** Doble clic en `iniciar_silencioso.vbs` (levanta el servidor REST, el motor guardián y la mascota sin ventanas de consola visibles).
- **Detener:** Doble clic en `detener_silencioso.vbs` (cierra ordenadamente todos los procesos secundarios).

### Verificación Automatizada (Tests)
Para auditar la validez del código:
```powershell
# 1. Pruebas del motor de atención y mascota (285 tests)
python -m pytest "YourFocusGuard/tests"

# 2. Pruebas de integración del servidor asistente (101 tests)
python "adhd-assistant/pruebas_automaticas.py"
```

---

## 4. Manifiesto de Recursos Excluidos del ZIP de Auditoría

Para evitar transferir un archivo de **~800 MB** que complicaría la revisión de código, se excluyeron deliberadamente los siguientes artefactos no esenciales para la lógica del programa:

| Recurso / Carpeta | Peso Aprox. | ¿Por qué se sacó? | ¿Cómo se regenera o afecta? |
| :--- | :---: | :--- | :--- |
| **`rea-analysis/`** | **~643.5 MB** | Volcado de sesiones de ingeniería inversa, desensamblado y binarios de inspección estática de herramientas externas. No forma parte del código operativo de la aplicación. | No afecta en nada al funcionamiento del asistente ni a sus pruebas unitarias. |
| **`panel_static/pets/` (58 carpetas alternas)** | **~93.4 MB** | Spritesheets y secuencias PNG de mascotas cosméticas adicionales (Goku, Nezuko, Kakashi, Zoro, Pikachu, Wall-E, etc.). | **Se conservó intacta la mascota activa (`einstein/`, ~1.8 MB)** para que la UI nativa y web funcionen y se auditen perfectamente. Los demás skins son activos estéticos opcionales. |
| **`data/fotos/` y capturas de cámara** | **~5.5 MB** | Fotografías temporales tomadas por webcam en pruebas locales para verificar algoritmos de presencia facial. | Contienen imágenes del entorno local de pruebas. El sistema las vuelve a crear automáticamente en tiempo de ejecución si la webcam está habilitada. |
| **`.git/` (Base de datos Git)** | **~50.0 MB** | Historial de commits y packfiles binarios de control de versiones. | El código entregado representa el estado final auditado (`main`). |
| **`_pytmp/`, `.pytest_cache/`, `__pycache__/`** | **~3.5 MB** | Archivos temporales generados durante la ejecución de las suites de pytest y bytecode compilado (`.pyc`). | Python genera el bytecode automáticamente al ejecutarse. |

### Balance de Peso
- **Peso original del directorio:** `~803 MB`
- **Peso del paquete de código auditado:** `< 5 MB` (reducción superior al 99%).
- **Integridad lógica:** El 100% del código ejecutable, configuraciones TOML, assets de Einstein y suites de pruebas están incluidos.
