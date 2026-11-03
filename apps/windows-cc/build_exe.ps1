param([string]$JarvisRoot = "C:\Users\rajk1\jarvis")
$ErrorActionPreference = "Stop"
Set-Location "$JarvisRoot\apps\windows-cc"
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
if (Test-Path "$JarvisRoot\apps\windows-panel\requirements.txt") {
  python -m pip install -r "$JarvisRoot\apps\windows-panel\requirements.txt"
}
# panel_api/voice from windows-panel; lib_jarvis + win scripts from scripts\win.
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Jarvis `
  --paths "$JarvisRoot\scripts\win" `
  --paths "$JarvisRoot\apps\windows-panel" `
  --paths "$JarvisRoot\apps\windows-cc" `
  --hidden-import panel_api --hidden-import bridge_api --hidden-import voice `
  --hidden-import metrics --hidden-import feed --hidden-import memory_index `
  --hidden-import llm_providers --hidden-import stt --hidden-import chat `
  --hidden-import agents --hidden-import agents.registry --hidden-import agents.worker `
  --hidden-import lib_jarvis --hidden-import session_start --hidden-import brief `
  --hidden-import workday_start --hidden-import block_delete `
  --hidden-import yaml --hidden-import runpy --hidden-import argparse `
  --hidden-import webview --hidden-import psutil `
  --hidden-import speech_recognition --hidden-import pyaudio `
  --collect-all speech_recognition `
  --hidden-import pyttsx3 --hidden-import pyttsx3.drivers --hidden-import pyttsx3.drivers.sapi5 `
  --hidden-import win32com.client --hidden-import pythoncom `
  --icon ..\windows-panel\assets\jarvis.ico --add-data "ui;ui" `
  --collect-all webview `
  host_main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
New-Item -ItemType Directory -Force -Path "$JarvisRoot\apps" | Out-Null
Copy-Item -Force ".\dist\Jarvis.exe" "$JarvisRoot\apps\Jarvis.exe"
$desk = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$desk\JARVIS.lnk")
$sc.TargetPath = "$JarvisRoot\apps\Jarvis.exe"
$sc.WorkingDirectory = "$JarvisRoot"
$sc.IconLocation = "$JarvisRoot\apps\Jarvis.exe,0"
$sc.Save()
Write-Output "INSTALLED=$JarvisRoot\apps\Jarvis.exe"
