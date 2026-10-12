@echo off
rem Poke-Controller Modified Extension (monitor tool)
rem   Python does not need to be installed: uv prepares Python and the libraries in the .venv folder.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" powershell -NoProfile -ExecutionPolicy Bypass -File "bootstrap\setup.ps1"
if not exist ".venv\Scripts\python.exe" ( pause & exit /b 1 )
rem Keep the next commands on one line (this file may be replaced by an update while it is running).
".venv\Scripts\python.exe" -m bootstrap monitor %* & pause & exit /b
