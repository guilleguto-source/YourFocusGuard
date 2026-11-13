Set WshShell = CreateObject("WScript.Shell")

' 1. Iniciar Servidor Core ADHD Assistant (8765) de forma silenciosa e independiente
WshShell.CurrentDirectory = "C:\Users\Guill\Documents\antigravity\ADHD Assistant"
WshShell.Run chr(34) & "C:\Program Files\Python312\pythonw.exe" & chr(34) & " " & chr(34) & "C:\Users\Guill\Documents\antigravity\ADHD Assistant\adhd-assistant\app\server.py" & chr(34), 0, False

' 2. Iniciar YourFocusGuard con Mascota Flotante Einstein (8756)
WshShell.CurrentDirectory = "C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard"
WshShell.Run chr(34) & "C:\Program Files\Python312\pythonw.exe" & chr(34) & " run.py start", 0, False

Set WshShell = Nothing
