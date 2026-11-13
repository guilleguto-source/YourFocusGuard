@echo off
setlocal
cd /d "C:\Users\Guill\Documents\antigravity\ADHD Assistant"

rem 1. Iniciar Servidor Core ADHD Assistant en puerto 8765
start "" "C:\Program Files\Python312\pythonw.exe" "adhd-assistant\app\server.py"

rem 2. Iniciar YourFocusGuard y Mascota Flotante en puerto 8756
cd /d "C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard"
if not exist "logs" mkdir "logs"
start "" "C:\Program Files\Python312\pythonw.exe" run.py start
