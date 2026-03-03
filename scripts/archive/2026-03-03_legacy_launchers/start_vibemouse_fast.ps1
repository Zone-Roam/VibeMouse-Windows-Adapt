$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startScript = Join-Path $scriptDir "start_vibemouse.ps1"

if (-not (Test-Path $startScript)) {
  Write-Host "[ERROR] Missing launcher: $startScript" -ForegroundColor Red
  exit 1
}

$env:VIBEMOUSE_BACKEND = "funasr_onnx"
$env:VIBEMOUSE_MODEL = "iic/SenseVoiceSmall"
$env:VIBEMOUSE_GESTURES_ENABLED = "false"
$env:VIBEMOUSE_GESTURE_FREEZE_POINTER = "false"
$env:VIBEMOUSE_GESTURE_RESTORE_CURSOR = "false"
Write-Host "[INFO] Profile: FAST (funasr_onnx + iic/SenseVoiceSmall)"

& $startScript
exit $LASTEXITCODE
