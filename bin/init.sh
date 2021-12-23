#!/usr/bin/env bash
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    echo "Created a virtual environment at ${PWD}/.venv"
fi

source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
deactivate
