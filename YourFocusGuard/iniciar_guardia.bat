@echo off
cd /d "C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard"
if not exist "logs" mkdir "logs"
"C:\Program Files\Python312\pythonw.exe" run.py start > "logs\arranque.log" 2>&1
