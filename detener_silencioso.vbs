Set WshShell = CreateObject("WScript.Shell")

WshShell.CurrentDirectory = "C:\Users\Guill\Documents\antigravity\ADHD Assistant\YourFocusGuard"
WshShell.Run chr(34) & "C:\Program Files\Python312\python.exe" & chr(34) & " run.py stop", 0, True
WshShell.Run "powershell.exe -NoProfile -WindowStyle Hidden -Command ""Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*server.py*' -or $_.CommandLine -like '*YourFocusGuard*' -or $_.CommandLine -like '*desktop_pet_native*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }""", 0, True

Set WshShell = Nothing
