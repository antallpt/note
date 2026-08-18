@echo off
rem Launcher (Windows): startet note mit dem venv-Python des Projekts.
"%~dp0.venv\Scripts\python.exe" "%~dp0app.py" %*
