#!/usr/bin/env sh
# Runs the file automation job (organize + merge). Point cron at this file.
# Python used: $PYTHON if set, else .venv/bin/python if it exists, else python3.
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
PY="${PYTHON:-python3}"
[ -z "$PYTHON" ] && [ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" file_automator.py run --config config.toml >> logs/scheduled.log 2>&1
