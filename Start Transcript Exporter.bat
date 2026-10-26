@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Transcript Exporter...
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 goto setup_error
)

".venv\Scripts\python.exe" -c "import tkinter; from importlib.metadata import version; assert version('youtube-transcript-api') == '1.2.4'" >nul 2>nul
if errorlevel 1 (
    echo Installing the transcript library. Internet access is required for setup.
    ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>nul
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto setup_error
)

start "Transcript Exporter" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
exit /b 0

:setup_error
echo.
echo Setup failed. Install Python 3.10 through 3.14 from https://www.python.org/downloads/
echo Include Tcl/Tk and pip in the installation, check your connection, and try again.
pause
exit /b 1
