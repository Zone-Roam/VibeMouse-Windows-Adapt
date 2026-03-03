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

if (-not $env:VIBEMOUSE_BACKEND) { $env:VIBEMOUSE_BACKEND = "funasr_onnx" }
if (-not $env:VIBEMOUSE_MODEL) { $env:VIBEMOUSE_MODEL = "iic/SenseVoiceSmall" }
if (-not $env:VIBEMOUSE_DEVICE) { $env:VIBEMOUSE_DEVICE = "cpu" }
if (-not $env:VIBEMOUSE_LANGUAGE) { $env:VIBEMOUSE_LANGUAGE = "auto" }
if (-not $env:VIBEMOUSE_USE_ITN) { $env:VIBEMOUSE_USE_ITN = "true" }
if (-not $env:VIBEMOUSE_AUTO_PASTE) { $env:VIBEMOUSE_AUTO_PASTE = "true" }
if (-not $env:VIBEMOUSE_INPUT_MODE) { $env:VIBEMOUSE_INPUT_MODE = "mouse" }
if (-not $env:VIBEMOUSE_FRONT_BUTTON) { $env:VIBEMOUSE_FRONT_BUTTON = "x2" }
if (-not $env:VIBEMOUSE_REAR_BUTTON) { $env:VIBEMOUSE_REAR_BUTTON = "x1" }
if (-not $env:VIBEMOUSE_FRONT_HOTKEY) { $env:VIBEMOUSE_FRONT_HOTKEY = "<ctrl>+<alt>+<shift>+f9" }
if (-not $env:VIBEMOUSE_REAR_HOTKEY) { $env:VIBEMOUSE_REAR_HOTKEY = "<ctrl>+<alt>+<shift>+f10" }
if (-not $env:PYTHONUNBUFFERED) { $env:PYTHONUNBUFFERED = "1" }

if (-not $env:VIBEMOUSE_OPENCLAW_ROUTE_MODE) { $env:VIBEMOUSE_OPENCLAW_ROUTE_MODE = "toggle" }
if (-not $env:VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL) { $env:VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL = "false" }
if (-not $env:VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY) { $env:VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY = "f8" }
if (-not $env:VIBEMOUSE_OPENCLAW_COMMAND) { $env:VIBEMOUSE_OPENCLAW_COMMAND = "wsl -d Ubuntu -- openclaw" }

$env:VIBEMOUSE_STATUS_FILE = Join-Path $runtimeDir "vibemouse-status.json"

Write-Host "[INFO] Starting VibeMouse..."
Write-Host "[INFO] Input mode: $($env:VIBEMOUSE_INPUT_MODE)"
Write-Host "[INFO] Toggle OpenClaw route hotkey: F8"
Write-Host "[INFO] Status file: $($env:VIBEMOUSE_STATUS_FILE)"
Write-Host ""

& $venvPython -u -m vibemouse.main run
exit $LASTEXITCODE
