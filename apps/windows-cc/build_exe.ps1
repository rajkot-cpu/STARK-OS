param([string]$JarvisRoot = "C:\Users\rajk1\jarvis")
$ErrorActionPreference = "Stop"
Set-Location "$JarvisRoot\apps\windows-cc"
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
# Wake word: ONNX-only, without scipy/scikit-learn (training-only deps).
python -m pip install --no-deps "openwakeword==0.4.0"
if ($LASTEXITCODE -ne 0) { throw "pip install openwakeword failed" }
if (Test-Path "$JarvisRoot\apps\windows-panel\requirements.txt") {
  python -m pip install -r "$JarvisRoot\apps\windows-panel\requirements.txt"
}
# Resolve MSVC runtime DLLs from System32 first: an old msvcp140.dll (14.27, e.g. from a
# JDK on PATH) gets bundled otherwise and crashes onnxruntime/ctranslate2 (0xc0000005).
$env:PATH = "$env:SystemRoot\System32;" + $env:PATH
# panel_api/voice from windows-panel; lib_jarvis + win scripts from scripts\win.
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Jarvis `
  --paths "$JarvisRoot\scripts\win" `
  --paths "$JarvisRoot\apps\windows-panel" `
  --paths "$JarvisRoot\apps\windows-cc" `
  --hidden-import panel_api --hidden-import bridge_api --hidden-import voice `
  --hidden-import metrics --hidden-import feed --hidden-import memory_index `
  --hidden-import llm_providers --hidden-import readiness --hidden-import stt --hidden-import chat `
  --hidden-import agents --hidden-import agents.registry --hidden-import agents.worker --hidden-import agent_tools --hidden-import shell_gate --hidden-import voice_intents `
  --hidden-import lib_jarvis --hidden-import session_start --hidden-import brief `
  --hidden-import workday_start --hidden-import block_delete `
  --hidden-import yaml --hidden-import runpy --hidden-import argparse `
  --hidden-import webview --hidden-import psutil `
  --hidden-import speech_recognition --hidden-import pyaudio `
  --collect-all speech_recognition `
  --hidden-import pyttsx3 --hidden-import pyttsx3.drivers --hidden-import pyttsx3.drivers.sapi5 `
  --hidden-import win32com.client --hidden-import pythoncom `
  --hidden-import cc_settings --hidden-import tts --hidden-import wakeword --hidden-import mcp_client `
  --hidden-import web_search --hidden-import screen --hidden-import winsound `
  --hidden-import openwakeword --hidden-import openwakeword.model --hidden-import openwakeword.utils `
  --hidden-import openwakeword.vad --collect-data openwakeword `
  --exclude-module scipy --exclude-module sklearn --exclude-module torch --exclude-module tflite_runtime `
  --collect-binaries onnxruntime --hidden-import onnxruntime `
  --collect-all faster_whisper --collect-binaries ctranslate2 --collect-submodules ctranslate2 `
  --collect-submodules av --hidden-import tokenizers --collect-submodules huggingface_hub `
  --collect-all edge_tts --hidden-import aiohttp `
  --collect-submodules mss --hidden-import PIL.Image `
  --hidden-import mcp --collect-submodules mcp.client --collect-submodules mcp.shared --collect-submodules mcp.os --hidden-import mcp.types --collect-submodules mcp_types --collect-submodules anyio `
  --collect-all ddgs --collect-binaries primp --hidden-import primp --hidden-import lxml `
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
