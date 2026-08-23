#!/usr/bin/env bash
# Convenience wrapper: runs LeadMap inside the project's virtualenv.
#   ./run.sh -l "Austin, TX" -c "coffee shop" -o cafes.csv
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Creating virtualenv…"; python3 -m venv .venv; }
.venv/bin/python -m pip install --quiet -r requirements.txt
exec .venv/bin/python -m leadmap "$@"
