@echo off
title HeyPC
cd /d "%~dp0"
.venv\Scripts\python.exe -m heypc.app
pause
