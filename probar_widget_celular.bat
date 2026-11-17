@echo off
chcp 65001 >nul
title [TEST] Asistente TDAH - Widget Movil (Nubia Z17 Lite)
echo =====================================================================
echo  📱 ENTORNO AISLADO DE PRUEBAS: WIDGET MOVIL (Estilo Desk Panel)
echo =====================================================================
echo.
echo Este lanzador es EXCLUSIVO para pruebas del celular (sin alterar tu PC).
echo.

:: Verificar si ADB esta disponible para enlace USB de baja latencia
where adb >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [1/3] Verificando conexion USB con Nubia Z17 Lite...
    adb reverse tcp:8765 tcp:8765 >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        echo  --^> Enlace USB detectado: 'adb reverse tcp:8765 tcp:8765' ACTIVO.
        echo  --^> En el celular puedes abrir directamente: http://localhost:8765/widget
    ) else (
        echo  --^> ADB disponible pero sin telefono conectado por cable (o sin depuracion USB).
    )
) else (
    echo [!] ADB no detectado en el PATH. Para usar cable USB, anade adb al PATH.
)
echo.

echo [2/3] Configurando modo de red:
echo  1. Solo USB / Localhost (Max segura, sin abrir puertos en tu router/Wi-Fi)
echo  2. Modo Wi-Fi (Expuesto en red local con codigo QR y clave emparejada)
echo.
set /p MODO_RED="Selecciona una opcion (1 o 2, por defecto 1): "

if "%MODO_RED%"=="2" (
    echo.
    echo [3/3] Iniciando con ASISTENTE_EXPUESTO_RED=1...
    set ASISTENTE_EXPUESTO_RED=1
) else (
    echo.
    echo [3/3] Iniciando en localhost puro (seguro para USB)...
    set ASISTENTE_EXPUESTO_RED=0
)

echo.
echo Presiona Ctrl+C en esta ventana para detener la prueba en cualquier momento.
echo =====================================================================
echo.
python adhd-assistant\app\server.py
pause
