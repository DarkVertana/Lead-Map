#!/usr/bin/env pwsh
# Business Lead on Windows (PowerShell). Same job as run.sh: make the virtualenv if it
# isn't there, install what's missing, then run.
#
#   .\run.ps1
#   .\run.ps1 -l "Austin, TX, USA" -c "coffee shop" -o cafes.csv

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# The ⏺ ⎿ ▰ ✻ this prints are UTF-8; older consoles need telling. The env var
# can't fail and stays outside the try — hosts where the console setter throws
# (ISE, remoting) are exactly the ones that need it most.
$env:PYTHONIOENCODING = "utf-8"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtualenv..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    }
    # Checked by result, not by which command existed: on a bare Windows the
    # Microsoft Store alias answers to "python" but installs nothing.
    if (-not (Test-Path $venvPython)) {
        Write-Error "No working Python found. Install Python 3.10+ from python.org or the Microsoft Store, then run this again."
        exit 1
    }
}

& $venvPython -m pip install --quiet --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Installing the requirements failed (are you online?). Fix the error above and run this again."
    exit $LASTEXITCODE
}
& $venvPython -m businesslead @args
exit $LASTEXITCODE
