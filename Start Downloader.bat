@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\pythonw.exe" (
    echo Project environment missing. Follow the setup steps in readme.md.
    pause
    exit /b 1
)
start "" "venv\Scripts\pythonw.exe" "%~dp0gui.py"
