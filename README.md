# Asistente TDAH + YourFocusGuard
> **Suite de asistencia para TDAH: asistente por voz en la PC + panel táctil en tu celular.** 🧠⚡

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Google Calendar](https://img.shields.io/badge/Google%20Calendar-API%20v3-red?logo=googlecalendar&logoColor=white)](https://developers.google.com/calendar)
[![Vikunja](https://img.shields.io/badge/Vikunja-Self--Hosted-blueviolet)](https://vikunja.io)
[![Status](https://img.shields.io/badge/Status-Active%20Development-success)]()

---

## 🎯 ¿Qué es YourFocusGuard?

**YourFocusGuard** es un asistente diseñado específicamente para contrarrestar la disfunción ejecutiva, la ceguera temporal y las distracciones recurrentes en personas con TDAH. 

Combina interacción por voz ultrarrápida, sincronización dual de tareas, reproducción de frecuencias de enfoque (ruido marrón y YouTube sin distracciones) y recordatorios contextuales en una interfaz reactiva.

---

## 🗂️ Dos aplicaciones, un solo proyecto

Este repositorio contiene **dos aplicaciones independientes** — instala la que necesites:

| Carpeta | Qué es | Instalar si quieres... |
| :--- | :--- | :--- |
| `adhd-assistant/` | **El producto principal** (v0.12.1): asistente por voz con Groq, tareas (Vikunja + Google Calendar), notas/briefing, alarmas, audio de enfoque y **widget para el celular** | El asistente y su panel web, en cualquier PC |
| `YourFocusGuard/` | Guardián de foco para Windows (v0.8.5): vigilancia de ventana activa, escalera de desvíos, mascota de escritorio, modo concentración | La vigilancia automática en tu PC Windows |

Ambos son locales y sin nube obligatoria; `adhd-assistant` no depende de `YourFocusGuard` para funcionar. El guardián está en modo mantenimiento (correcciones, sin features nuevas).

## 📱 Widget en el celular (estilo PhoneBox)

El asistente sirve un **panel táctil para el celular** sin instalar ninguna app: el navegador del teléfono hace de WebView y "Agregar a pantalla de inicio" lo deja como ícono tipo app.

1. Empareja por Wi-Fi: ejecuta el asistente con `ASISTENTE_EXPUESTO_RED=1` (variable de entorno) — en la consola aparece la URL `http://TU-IP:8765/widget?t=CLAVE` y un **QR** escaneable (si instalaste `qrcode`).
2. En el celular abre esa URL (la clave emparejada vive en `data/sesion_token.json`; bórrala para desemparejar todo).
3. En Chrome/Edge del celular: menú → **Agregar a pantalla de inicio** → se instala como app a pantalla completa.

El widget da: briefing del día, alarmas rápidas (+5/+15/+30/+1h y personalizadas, cancelables), tareas pendientes con check y alta de tareas, y notas rápidas (brain dump). Sin el modo red, el widget también funciona en la misma PC en `http://localhost:8765/widget`.

---

## ✨ Características Principales

### 📅 1. Google Calendar & Extracción Natural
* **Comprensión Temporal Relativa:** Convierte órdenes como *"Agenda cita médica mañana a las 10am"* o *"Reunión el viernes a las 3pm"* en fechas exactas ISO 8601 con zona horaria local.
* **OAuth 2.0 Nativo:** Conexión persistente mediante tokens renovables.

### 📋 2. Sincronización Dual de Tareas (Vikunja + Google)
* **Gestión de Prioridades:** Clasificación de tareas en 🚨 Urgente, 🔥 Alta, ⚡ Normal y ☕ Baja.
* **Modo Espejo:** Cualquier tarea creada o completada se sincroniza simultáneamente en tu servidor autohospedado **Vikunja** y en **Google**.
* **Organización de Cronograma:** Pregunta *"¿Qué me toca hacer ahora?"* para obtener tu lista ordenada por impacto y urgencia.

### ⏰ 3. Alarmas y Temporizadores en Segundo Plano
* Temporizadores en lenguaje natural: *"Pon una alarma en 2 horas que diga llamar a mamá"*.
* Alertas acústicas y visuales en pantalla al cumplirse el plazo.

### 🎧 4. Centro de Audio & Enfoque TDAH
* **Ruido Marrón / Blanco / Rosa:** Generador matemático local offline con 0 ms de latencia (frecuencias clínicamente recomendadas para enfoque TDAH).
* **YouTube Streaming Libre:** Extracción de audio directo sin anuncios ni ventanas invasivas vía `yt-dlp`.

### 🎙️ 5. Interfaz Visual Moderna (Glassmorphism)
* **Feedback de Micrófono en Vivo:** Visualizador de ondas de audio en Canvas que te muestra en tiempo real cuándo el asistente está escuchando y procesando.
* **Microinteracciones Táctiles:** Efectos *ripple* y compresión física en cada botón.
* **Síntesis de Voz (TTS):** Confirmación verbal al auricular de cada acción ejecutada.

---

## 🚀 Inicio Rápido

### Requisitos Previos
* Python 3.11 o 3.12
* Claves de API: Groq API Key (o Gemini)
* Credenciales de Google Calendar (`credentials.json`)

### Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/guilleguto-source/YourFocusGuard.git
cd YourFocusGuard

# 2. Instalar dependencias
pip install -r adhd-assistant/requirements.txt

# 3. Configurar entorno (.env)
cp adhd-assistant/.env.example adhd-assistant/.env
# Edita adhd-assistant/.env con tus claves
```

### Ejecutar el Asistente

```bash
# Iniciar el panel web reactivo (http://localhost:8765)
python adhd-assistant/app/server.py
```

---

## 🔒 Privacidad y Seguridad

* **Sin rastreo invasivo:** No se transmiten datos innecesarios a servidores de terceros.
* **Tokens locales:** Las credenciales de Google y Vikunja se almacenan cifradas localmente en tu equipo.

---

## 📄 Licencia

Distribuido bajo la Licencia MIT. Consulta `LICENSE` para más detalles.
