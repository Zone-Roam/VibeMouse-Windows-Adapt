$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
  Write-Host "[ERROR] Python virtual environment not found: $venvPython" -ForegroundColor Red
  Write-Host "Please run: py -3.11 -m venv .venv" -ForegroundColor Yellow
  exit 1
}

$runtimeDir = Join-Path $projectRoot ".runtime"
if (-not (Test-Path $runtimeDir)) {
  New-Item -ItemType Directory -Path $runtimeDir | Out-Null
}

$env:VIBEMOUSE_BACKEND = "funasr_onnx"
$env:VIBEMOUSE_MODEL = "iic/SenseVoiceSmall"
$env:VIBEMOUSE_DEVICE = "cpu"
$env:VIBEMOUSE_LANGUAGE = "auto"
$env:VIBEMOUSE_USE_ITN = "true"
$env:VIBEMOUSE_AUTO_PASTE = "true"
$env:VIBEMOUSE_FRONT_BUTTON = "x2"
$env:VIBEMOUSE_REAR_BUTTON = "x1"
$env:PYTHONUNBUFFERED = "1"

$env:VIBEMOUSE_OPENCLAW_ROUTE_MODE = "toggle"
$env:VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL = "false"
$env:VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY = "f8"
$env:VIBEMOUSE_OPENCLAW_COMMAND = "wsl -d Ubuntu -- openclaw"

$env:VIBEMOUSE_STATUS_FILE = Join-Path $runtimeDir "vibemouse-status.json"

Write-Host "[INFO] Starting VibeMouse..."
Write-Host "[INFO] Toggle OpenClaw route hotkey: F8"
Write-Host "[INFO] Status file: $($env:VIBEMOUSE_STATUS_FILE)"
Write-Host ""

& $venvPython -u -m vibemouse.main run
exit $LASTEXITCODE
