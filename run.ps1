#!/usr/bin/env pwsh
# LeadMap on Windows (PowerShell). Same job as run.sh: make the virtualenv if it
# isn't there, install what's missing, then run.
#
#   .\run.ps1
#   .\run.ps1 -l "Austin, TX" -c "coffee shop" -o cafes.csv

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# The ⏺ ⎿ ▰ ✻ this prints are UTF-8; older consoles need telling.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = "utf-8"
} catch { }

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtualenv..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        Write-Error "No Python found. Install Python 3.10+ from python.org or the Microsoft Store."
        exit 1
    }
}

& $venvPython -m pip install --quiet --disable-pip-version-check -r requirements.txt
& $venvPython -m leadmap @args
exit $LASTEXITCODE
