#!/usr/bin/env bash
# Creates a virtual environment and installs requirements for the service.

echo "Initializing requirements for crowdnalysis-service..."

# Create a virtual env
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    echo "Created a virtual environment at ${PWD}/.venv"
fi

# Install requirements
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# Install CmdStan CLI
CMDSTAN_DIR="$HOME/.cmdstan"
if [[ "$OSTYPE" == "linux-gnu"*  ||  "$OSTYPE" == "darwin"* ]]; then
  if [[ ! -d "$CMDSTAN_DIR" ]]; then
    echo "Installing CmdStan library into '${CMDSTAN_DIR}', please wait..."
    install_cmdstan -d $CMDSTAN_DIR
    echo "CmdStan library installed."
  else
    echo "CmdStan library already installed at '${CMDSTAN_DIR}'."
  fi
fi

deactivate  # the virtual env

echo "Initialization completed."
