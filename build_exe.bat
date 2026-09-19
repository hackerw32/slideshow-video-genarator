@echo off
setlocal
title Build EXE - Slideshow Video Creator Pro
echo Building a new standalone .exe (this can take a few minutes)...
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1" %*
echo.
echo Build window finished. Press any key to close.
pause >nul
