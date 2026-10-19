@echo off
setlocal
title Mouse Interaction Automator - Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set "STATUS=%ERRORLEVEL%"
if not "%STATUS%"=="0" (
  echo.
  echo Setup did not finish. Please read the error above.
  pause
)
exit /b %STATUS%
