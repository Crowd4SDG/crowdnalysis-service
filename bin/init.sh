#!/usr/bin/env bash
echo "Initializing requirements for crowdnalysis-service..."

# Create a virtual env
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    echo "Created a virtual environment at ${PWD}/.venv"
fi

source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
deactivate

# Install CmdStan CLI
CMDSTAN_DIR="$HOME/.cmdstan"
CMDSTAN_VER="2.26.1"
if [[ "$OSTYPE" == "linux-gnu"*  ||  "$OSTYPE" == "darwin"* ]]; then
  if [[ ! -d "$CMDSTAN_DIR" ]]; then
    echo "Installing CmdStan library into '${CMDSTAN_DIR}', please wait..."
    install_cmdstan -d $CMDSTAN_DIR  -v $CMDSTAN_VER
    echo "CmdStan library installed (v${CMDSTAN_VER})."
  else
    echo "CmdStan library already installed in '${CMDSTAN_DIR}'."
  fi
fi

# Create the env variable used by the service
export PYBOSSA_API_HOST=${NGINX_HOST:-localhost}

echo "Initialization completed."
