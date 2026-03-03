@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VIBEMOUSE_BACKEND=funasr_onnx"
set "VIBEMOUSE_MODEL=iic/SenseVoiceSmall"
set "VIBEMOUSE_GESTURES_ENABLED=false"
set "VIBEMOUSE_GESTURE_FREEZE_POINTER=false"
set "VIBEMOUSE_GESTURE_RESTORE_CURSOR=false"

echo [INFO] Tray profile: FAST (funasr_onnx + iic/SenseVoiceSmall)
start "" wscript.exe "%SCRIPT_DIR%start_vibemouse_tray.vbs"
exit /b %ERRORLEVEL%
