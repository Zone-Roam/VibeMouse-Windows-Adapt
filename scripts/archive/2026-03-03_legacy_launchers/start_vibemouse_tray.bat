@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
start "" wscript.exe "%SCRIPT_DIR%start_vibemouse_tray.vbs"
exit /b %ERRORLEVEL%
