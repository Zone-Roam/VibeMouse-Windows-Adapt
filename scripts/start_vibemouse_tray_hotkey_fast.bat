@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VIBEMOUSE_BACKEND=funasr_onnx"
set "VIBEMOUSE_MODEL=iic/SenseVoiceSmall"
set "VIBEMOUSE_INPUT_MODE=hotkey"
set "VIBEMOUSE_FRONT_HOTKEY=<ctrl>+<alt>+<shift>+f9"
set "VIBEMOUSE_REAR_HOTKEY=<ctrl>+<alt>+<shift>+f10"
set "VIBEMOUSE_GESTURES_ENABLED=false"
set "VIBEMOUSE_GESTURE_FREEZE_POINTER=false"
set "VIBEMOUSE_GESTURE_RESTORE_CURSOR=false"
set "VIBEMOUSE_WINDOWS_CURSOR_TERMINAL_MODE=true"

echo [INFO] Tray profile: HOTKEY FAST (funasr_onnx + iic/SenseVoiceSmall)
echo [INFO] Front hotkey: %VIBEMOUSE_FRONT_HOTKEY%
echo [INFO] Rear hotkey: %VIBEMOUSE_REAR_HOTKEY%
start "" wscript.exe "%SCRIPT_DIR%start_vibemouse_tray.vbs"
exit /b %ERRORLEVEL%
