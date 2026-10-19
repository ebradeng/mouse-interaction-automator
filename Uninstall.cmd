@echo off
setlocal
title Mouse Interaction Automator - Uninstall
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
if errorlevel 1 (echo. & pause)
