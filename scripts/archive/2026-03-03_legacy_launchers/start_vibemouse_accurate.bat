@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "START_SCRIPT=%SCRIPT_DIR%start_vibemouse.bat"

if not exist "%START_SCRIPT%" (
  echo [ERROR] Missing launcher: "%START_SCRIPT%"
  exit /b 1
)

set "VIBEMOUSE_BACKEND=funasr"
set "VIBEMOUSE_MODEL=iic/SenseVoiceSmall"
set "VIBEMOUSE_GESTURES_ENABLED=false"
set "VIBEMOUSE_GESTURE_FREEZE_POINTER=false"
set "VIBEMOUSE_GESTURE_RESTORE_CURSOR=false"
echo [INFO] Profile: ACCURATE (funasr + iic/SenseVoiceSmall)

call "%START_SCRIPT%"
exit /b %ERRORLEVEL%
