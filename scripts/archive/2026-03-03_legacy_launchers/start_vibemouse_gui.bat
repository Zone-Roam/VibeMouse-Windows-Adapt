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

"%VENV_PYTHON%" "%SCRIPT_DIR%run_gui.py"
exit /b %ERRORLEVEL%
