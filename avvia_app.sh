#!/usr/bin/env bash
# ============================================================
#  Avvio MoneyBoard (macOS / Linux)
#  Al primo avvio crea l'ambiente Python e installa i pacchetti;
#  poi apre l'app nel browser.   Uso: ./avvia_app.sh [aggiorna]
# ============================================================
set -u
cd "$(dirname "$0")"
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/MoneyBoard/venv"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
    echo "Prima installazione: creo l'ambiente Python in $VENV ..."
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3 non trovato. Installalo da https://www.python.org/downloads/"
        exit 1
    fi
    mkdir -p "$(dirname "$VENV")"
    if ! python3 -m venv "$VENV"; then
        echo "Non riesco a creare l'ambiente Python (su Debian/Ubuntu: sudo apt install python3-venv)."
        exit 1
    fi
    "$PY" -m pip install --upgrade pip
    if ! "$PY" -m pip install -r requirements.txt; then
        echo "Installazione dei pacchetti non riuscita."
        rm -rf "$VENV"
        exit 1
    fi
    cp requirements.txt "$VENV/requirements.installati.txt"
fi

if [ "${1:-}" = "aggiorna" ]; then
    "$PY" -m pip install --upgrade -r requirements.txt
fi

# Se l'elenco dei pacchetti e' cambiato (nuove funzioni), installa quelli mancanti
if ! cmp -s requirements.txt "$VENV/requirements.installati.txt"; then
    echo "Installo i pacchetti nuovi richiesti dall'app..."
    "$PY" -m pip install -r requirements.txt && cp requirements.txt "$VENV/requirements.installati.txt"
fi

exec "$PY" -m streamlit run app.py --server.headless false
