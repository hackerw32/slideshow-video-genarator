@echo off
setlocal
title Slideshow Video Creator - Installer
echo Starting the installer...
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
echo You can close this window now (press any key).
pause >nul
