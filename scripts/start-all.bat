@echo off
REM Double-click or run: scripts\start-all.bat
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" %*
pause
