@echo off
set "STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\YourFocusGuard.lnk"
if exist "%STARTUP_LNK%" (
    del "%STARTUP_LNK%"
    echo [OK] Autoarranque con Windows desactivado.
) else (
    echo [INFO] El acceso directo no estaba en la carpeta de Inicio.
)
pause
