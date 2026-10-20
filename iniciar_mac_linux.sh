#!/usr/bin/env bash
# Lanzador de EcoGuardian AI. Uso: bash iniciar_mac_linux.sh
cd "$(dirname "$0")"
if [ ! -d venv ]; then
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  source venv/bin/activate
fi
if [ -z "$ECOGUARDIAN_SETUP_KEY" ]; then
  read -r -s -p "Clave inicial de configuración (solo primera configuración): " ECOGUARDIAN_SETUP_KEY
  echo
  export ECOGUARDIAN_SETUP_KEY
fi
streamlit run app.py --server.address 0.0.0.0
