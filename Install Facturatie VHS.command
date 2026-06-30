#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is niet gevonden op deze Mac."
  echo "Installeer eerst Python 3 en start dit bestand daarna opnieuw."
  read -n 1 -s -r -p "Druk op een toets om af te sluiten..."
  echo
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Virtuele omgeving wordt aangemaakt..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Dependencies worden geinstalleerd of bijgewerkt..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "Installatie voltooid."
echo "Gebruik voortaan 'Start Facturatie VHS.command' om de app te openen."
read -n 1 -s -r -p "Druk op een toets om af te sluiten..."
echo
