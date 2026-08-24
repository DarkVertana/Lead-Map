@echo off
REM Business Lead on Windows (cmd.exe). Same job as run.sh.
REM   run.cmd
REM   run.cmd -l "Austin, TX, USA" -c "coffee shop" -o cafes.csv

setlocal
cd /d "%~dp0"

REM the box-drawing and ⏺ glyphs need a UTF-8 code page on older consoles
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtualenv...
    py -3 -m venv .venv || python -m venv .venv
)

REM checked by result: the Microsoft Store alias answers to "python" but
REM installs nothing, and a half-made venv is no venv at all.
if not exist ".venv\Scripts\python.exe" (
    echo No working Python found. Install Python 3.10+ from python.org or the
    echo Microsoft Store, then run this again.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Installing the requirements failed - are you online? Fix the error
    echo above and run this again.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m businesslead %*
exit /b %ERRORLEVEL%
