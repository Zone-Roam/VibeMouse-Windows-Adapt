@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "VENV_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
  echo [ERROR] Python virtual environment not found: "%VENV_PYTHON%"
  echo Please run: py -3.11 -m venv .venv
  exit /b 1
)

set "RUNTIME_DIR=%PROJECT_ROOT%\.runtime"
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

set "VIBEMOUSE_BACKEND=funasr_onnx"
set "VIBEMOUSE_MODEL=iic/SenseVoiceSmall"
set "VIBEMOUSE_DEVICE=cpu"
set "VIBEMOUSE_LANGUAGE=auto"
set "VIBEMOUSE_USE_ITN=true"

set "VIBEMOUSE_OPENCLAW_ROUTE_MODE=toggle"
set "VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL=false"
set "VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY=f8"
set "VIBEMOUSE_OPENCLAW_COMMAND=wsl -d Ubuntu -- openclaw"

set "VIBEMOUSE_STATUS_FILE=%RUNTIME_DIR%\vibemouse-status.json"

echo [INFO] Starting VibeMouse...
echo [INFO] Toggle OpenClaw route hotkey: F8
echo [INFO] Status file: "%VIBEMOUSE_STATUS_FILE%"
echo.

"%VENV_PYTHON%" -m vibemouse.main run
exit /b %ERRORLEVEL%
