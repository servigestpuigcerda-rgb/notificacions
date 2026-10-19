#!/bin/sh
# Arrenca l'aplicació. Accessible des del mòbil a http://<ip-del-pc>:8000
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
