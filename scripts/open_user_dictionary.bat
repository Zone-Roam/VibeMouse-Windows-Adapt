@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "RUNTIME_DIR=%PROJECT_ROOT%\.runtime"
set "DICT_FILE=%RUNTIME_DIR%\user_dictionary.json"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

if not exist "%DICT_FILE%" (
  >"%DICT_FILE%" (
    echo {
    echo   "_help": [
    echo     "Edit replacements to correct your common ASR mistakes.",
    echo     "Keys are matched case-insensitively."
    echo   ],
    echo   "replacements": {
    echo     "telegarm": "Telegram",
    echo     "open claw": "OpenClaw",
    echo     "chat g p t": "ChatGPT"
    echo   }
    echo }
  )
)

start "" notepad.exe "%DICT_FILE%"
exit /b %ERRORLEVEL%
