@echo off
setlocal
cd /d "C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard"
call "C:\Program Files\Python312\python.exe" run.py stop >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*server.py*' -or $_.CommandLine -like '*YourFocusGuard*' -or $_.CommandLine -like '*desktop_pet_native*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
