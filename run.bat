@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"

cd /d "%~dp0"
if errorlevel 1 (
  echo ERROR: Cannot switch to the skill directory.
  pause
  exit /b 1
)

where py.exe >nul 2>nul
if not errorlevel 1 (
  py -3.12 "%~dp0scripts\auto_change_password.py" %*
) else (
  python "%~dp0scripts\auto_change_password.py" %*
)
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo run.bat finished. Exit code: %EXIT_CODE%
echo If the Python output above mentions missing assets or recognition failure,
echo follow that guidance and use debug_tool.py when needed.
echo.
pause

exit /b %EXIT_CODE%
