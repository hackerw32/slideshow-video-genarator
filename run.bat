@echo off
setlocal
title Slideshow Video Creator
cd /d "%~dp0"
if exist "ffmpeg\ffmpeg.exe" set "PATH=%~dp0ffmpeg;%PATH%"
if not exist ".venv\Scripts\python.exe" goto :novenv
".venv\Scripts\python.exe" "slideshow_app v4.py"
if errorlevel 1 goto :apperr
exit /b 0

:novenv
echo.
echo [ERROR] The Python environment was not found.
echo Run install.bat first.
echo.
pause
exit /b 1

:apperr
echo.
echo The app exited with an error. Read the message above.
pause
exit /b 1
