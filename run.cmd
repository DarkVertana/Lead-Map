@echo off
REM LeadMap on Windows (cmd.exe). Same job as run.sh.
REM   run.cmd
REM   run.cmd -l "Austin, TX" -c "coffee shop" -o cafes.csv

setlocal
cd /d "%~dp0"

REM the box-drawing and ⏺ glyphs need a UTF-8 code page on older consoles
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtualenv...
    py -3 -m venv .venv || python -m venv .venv
    if errorlevel 1 (
        echo No Python found. Install Python 3.10+ from python.org or the Microsoft Store.
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
".venv\Scripts\python.exe" -m leadmap %*
exit /b %ERRORLEVEL%
