@echo off
title Jarvis
cd /d "%~dp0"
.venv\Scripts\python.exe -m jarvis.app
pause
