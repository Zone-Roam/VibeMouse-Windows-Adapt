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

if not defined VIBEMOUSE_BACKEND set "VIBEMOUSE_BACKEND=funasr_onnx"
if not defined VIBEMOUSE_MODEL set "VIBEMOUSE_MODEL=iic/SenseVoiceSmall"
if not defined VIBEMOUSE_DEVICE set "VIBEMOUSE_DEVICE=cpu"
if not defined VIBEMOUSE_LANGUAGE set "VIBEMOUSE_LANGUAGE=auto"
if not defined VIBEMOUSE_USE_ITN set "VIBEMOUSE_USE_ITN=true"
if not defined VIBEMOUSE_AUTO_PASTE set "VIBEMOUSE_AUTO_PASTE=true"
if not defined VIBEMOUSE_INPUT_MODE set "VIBEMOUSE_INPUT_MODE=mouse"
if not defined VIBEMOUSE_FRONT_BUTTON set "VIBEMOUSE_FRONT_BUTTON=x2"
if not defined VIBEMOUSE_REAR_BUTTON set "VIBEMOUSE_REAR_BUTTON=x1"
if not defined VIBEMOUSE_FRONT_HOTKEY set "VIBEMOUSE_FRONT_HOTKEY=<ctrl>+<alt>+<shift>+f9"
if not defined VIBEMOUSE_REAR_HOTKEY set "VIBEMOUSE_REAR_HOTKEY=<ctrl>+<alt>+<shift>+f10"
if not defined PYTHONUNBUFFERED set "PYTHONUNBUFFERED=1"

if not defined VIBEMOUSE_OPENCLAW_ROUTE_MODE set "VIBEMOUSE_OPENCLAW_ROUTE_MODE=toggle"
if not defined VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL set "VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL=false"
if not defined VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY set "VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY=f8"
if not defined VIBEMOUSE_OPENCLAW_COMMAND set "VIBEMOUSE_OPENCLAW_COMMAND=wsl -d Ubuntu -- openclaw"

set "VIBEMOUSE_STATUS_FILE=%RUNTIME_DIR%\vibemouse-status.json"

echo [INFO] Starting VibeMouse...
echo [INFO] Input mode: %VIBEMOUSE_INPUT_MODE%
echo [INFO] Toggle OpenClaw route hotkey: F8
echo [INFO] Status file: "%VIBEMOUSE_STATUS_FILE%"
echo.

"%VENV_PYTHON%" -u -m vibemouse.main run
exit /b %ERRORLEVEL%
