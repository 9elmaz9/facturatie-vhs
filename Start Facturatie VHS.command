#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8502}"
APP_URL="http://localhost:${PORT}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is niet gevonden op deze Mac."
  echo "Installeer eerst Python 3 en voer daarna de installatie opnieuw uit."
  read -n 1 -s -r -p "Druk op een toets om af te sluiten..."
  echo
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "De virtuele omgeving ontbreekt."
  echo "Open eerst 'Install Facturatie VHS.command'."
  read -n 1 -s -r -p "Druk op een toets om af te sluiten..."
  echo
  exit 1
fi

if lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Poort ${PORT} is al in gebruik."
  echo "Sluit de andere Streamlit-sessie of gebruik een andere poort."
  read -n 1 -s -r -p "Druk op een toets om af te sluiten..."
  echo
  exit 1
fi

source .venv/bin/activate

if ! python -c "import streamlit" >/dev/null 2>&1; then
  echo "Streamlit is nog niet beschikbaar."
  echo "Open eerst 'Install Facturatie VHS.command'."
  read -n 1 -s -r -p "Druk op een toets om af te sluiten..."
  echo
  exit 1
fi

echo "Facturatie VHS wordt gestart op ${APP_URL}"
python -m streamlit run app.py --server.headless true --server.port "${PORT}" &
STREAMLIT_PID=$!

sleep 3
open "${APP_URL}"

wait "${STREAMLIT_PID}"
