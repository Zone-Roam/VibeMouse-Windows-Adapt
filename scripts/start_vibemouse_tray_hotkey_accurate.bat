@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VIBEMOUSE_BACKEND=funasr"
set "VIBEMOUSE_MODEL=iic/SenseVoiceSmall"
set "VIBEMOUSE_INPUT_MODE=hotkey"
set "VIBEMOUSE_FRONT_HOTKEY=<ctrl>+<alt>+<shift>+f9"
set "VIBEMOUSE_REAR_HOTKEY=<ctrl>+<alt>+<shift>+f10"
set "VIBEMOUSE_GESTURES_ENABLED=false"
set "VIBEMOUSE_GESTURE_FREEZE_POINTER=false"
set "VIBEMOUSE_GESTURE_RESTORE_CURSOR=false"
set "VIBEMOUSE_WINDOWS_CURSOR_TERMINAL_MODE=true"
set "VIBEMOUSE_TRAY_MIC_OVERLAY=true"
set "VIBEMOUSE_TRANSLATION_TOGGLE_HOTKEY=none"
set "VIBEMOUSE_TRANSLATION_TOGGLE_INITIAL=false"
set "VIBEMOUSE_TRANSLATION_API_BASE=https://api.deepseek.com/v1"
set "VIBEMOUSE_TRANSLATION_MODEL=deepseek-chat"

if exist "%SCRIPT_DIR%local_api_keys.bat" (
  call "%SCRIPT_DIR%local_api_keys.bat"
)

echo [INFO] Tray profile: HOTKEY ACCURATE (funasr + iic/SenseVoiceSmall)
echo [INFO] Front hotkey: %VIBEMOUSE_FRONT_HOTKEY%
echo [INFO] Rear hotkey: %VIBEMOUSE_REAR_HOTKEY%
echo [INFO] Translation control: tray right-click menu
if "%VIBEMOUSE_TRANSLATION_API_KEY%"=="" (
  echo [WARN] Translation API key is empty. Create scripts\local_api_keys.bat to enable API translation.
)
start "" wscript.exe "%SCRIPT_DIR%start_vibemouse_tray.vbs"
exit /b %ERRORLEVEL%
