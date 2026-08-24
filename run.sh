#!/usr/bin/env bash
# Convenience wrapper: runs Business Lead inside the project's virtualenv.
#   ./run.sh -l "Austin, TX, USA" -c "coffee shop" -o cafes.csv
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Creating virtualenv…"; python3 -m venv .venv; }
# Git Bash on Windows makes a Scripts\ venv, not bin/ — take whichever exists.
PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/Scripts/python.exe
"$PY" -m pip install --quiet -r requirements.txt
exec "$PY" -m businesslead "$@"
